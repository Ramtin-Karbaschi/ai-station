from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

PROJECT_DIR = Path(os.getenv("AI_STATION_PROJECT_DIR", "/opt/ai-station"))
CATALOG_PATH = Path(os.getenv("AI_STATION_MODEL_CATALOG", str(PROJECT_DIR / "config/model-catalog.json")))

COMPOSE_BASE = [
    "docker",
    "compose",
    "--project-name", "ai-station",
    "--env-file", ".env.models",
    "-f", "compose.yml",
    "-f", "compose.models.yml",
    "-f", "compose.console.yml",
]

HEAVY_SERVICES = ["llm-general", "llm-coder", "llm-coder-next", "llm-thinking", "vlm"]
MODEL_LOCK = asyncio.Lock()
QUEUE: list[dict[str, Any]] = []
ACTIVE_MODEL_ID: str | None = None

app = FastAPI(title="AI Station Gateway", version="0.2.0")


def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def catalog_models() -> list[dict[str, Any]]:
    return load_catalog().get("models", [])


def normalize_model_id(model_id: str) -> str:
    # Open WebUI may prefix model names, e.g. gateway.general-qwen...
    if "." in model_id:
        return model_id.split(".")[-1]
    return model_id


def selectable_models() -> list[dict[str, Any]]:
    return [
        m for m in catalog_models()
        if m.get("enabled") is True and m.get("kind") in {"chat", "vision"}
    ]


def get_model(model_id: str) -> dict[str, Any]:
    model_id = normalize_model_id(model_id)
    for model in catalog_models():
        if model.get("id") == model_id and model.get("enabled") is True:
            return model
    raise HTTPException(status_code=404, detail=f"Unknown or disabled model: {model_id}")


def run_compose(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        COMPOSE_BASE + args,
        cwd=str(PROJECT_DIR),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


async def compose(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return await asyncio.to_thread(run_compose, args, timeout)


async def ensure_core() -> None:
    result = await compose(["up", "-d", "postgres", "redis", "api", "worker"], timeout=240)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail={
            "stage": "ensure_core",
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:]
        })


async def stop_other_heavy(target_service: str) -> None:
    to_stop = [s for s in HEAVY_SERVICES if s != target_service]
    if not to_stop:
        return

    await compose([
        "--profile", "llm-general",
        "--profile", "coder",
        "--profile", "thinking",
        "--profile", "vision",
        "stop",
        *to_stop,
    ], timeout=240)


async def wait_ready(model: dict[str, Any], attempts: int = 480) -> None:
    url = f"{model['base_url']}/models"

    async with httpx.AsyncClient(timeout=5) as client:
        last_error = None
        for _ in range(attempts):
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return
                last_error = f"HTTP {r.status_code}: {r.text[:500]}"
            except Exception as e:
                last_error = repr(e)

            await asyncio.sleep(2)

    raise HTTPException(status_code=503, detail={
        "stage": "wait_ready",
        "model": model["id"],
        "service": model.get("service"),
        "url": url,
        "last_error": last_error,
    })


async def start_runtime(model: dict[str, Any]) -> None:
    global ACTIVE_MODEL_ID

    if "service" not in model or "profile" not in model:
        raise HTTPException(status_code=400, detail=f"Model has no runtime service: {model['id']}")

    await ensure_core()

    if model.get("heavy"):
        await stop_other_heavy(model["service"])

    result = await compose(
        ["--profile", model["profile"], "up", "-d", model["service"]],
        timeout=300,
    )

    if result.returncode != 0:
        raise HTTPException(status_code=500, detail={
            "stage": "start_runtime",
            "model": model["id"],
            "service": model["service"],
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        })

    await wait_ready(model)

    if model.get("heavy"):
        ACTIVE_MODEL_ID = model["id"]


def rewrite_messages(model: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    body["model"] = model["backend_model"]

    prefix = model.get("default_system_prefix") or ""
    if prefix:
        messages = list(body.get("messages", []))
        messages.insert(0, {"role": "system", "content": prefix})
        body["messages"] = messages

    return body


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "0.2.0",
        "active_model_id": ACTIVE_MODEL_ID,
        "queue_length": len(QUEUE),
        "catalog_path": str(CATALOG_PATH),
        "models": [m["id"] for m in selectable_models()],
    }


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": m["id"],
                "object": "model",
                "created": 0,
                "owned_by": "ai-station",
                "root": m["id"],
                "parent": None,
                "permission": [],
            }
            for m in selectable_models()
        ],
    }


@app.get("/queue")
async def queue() -> dict[str, Any]:
    return {
        "active_model_id": ACTIVE_MODEL_ID,
        "queue_length": len(QUEUE),
        "queue": QUEUE,
    }


@app.post("/v1/chat/completions")
async def chat(request: Request):
    raw_body = await request.json()
    requested = raw_body.get("model")
    if not requested:
        raise HTTPException(status_code=400, detail="Missing model")

    model = get_model(requested)
    body = rewrite_messages(model, raw_body)

    request_id = str(uuid.uuid4())
    item = {
        "id": request_id,
        "model": model["id"],
        "state": "queued",
        "created_at": time.time(),
    }
    QUEUE.append(item)

    if bool(raw_body.get("stream", False)):
        return StreamingResponse(
            stream_proxy(request, model, body, item),
            media_type="text/event-stream",
        )

    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            await start_runtime(model)
            item["state"] = "running"

            async with httpx.AsyncClient(timeout=None) as client:
                r = await client.post(f"{model['base_url']}/chat/completions", json=body)
                try:
                    content = r.json()
                except Exception:
                    content = {"error": r.text}
                return JSONResponse(content=content, status_code=r.status_code)
    finally:
        if item in QUEUE:
            QUEUE.remove(item)


async def stream_proxy(
    request: Request,
    model: dict[str, Any],
    body: dict[str, Any],
    item: dict[str, Any],
) -> AsyncIterator[bytes]:
    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"

            # SSE keepalive while model cold-starts.
            yield b": AI Station is preparing the selected local model\n\n"

            await start_runtime(model)

            item["state"] = "running"

            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{model['base_url']}/chat/completions",
                    json=body,
                ) as r:
                    async for chunk in r.aiter_bytes():
                        if await request.is_disconnected():
                            break
                        yield chunk
    except Exception as e:
        payload = json.dumps({
            "error": {
                "message": str(e),
                "type": "ai_station_gateway_error"
            }
        }, ensure_ascii=False)
        yield f"data: {payload}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"
    finally:
        if item in QUEUE:
            QUEUE.remove(item)
