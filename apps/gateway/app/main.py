from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from apps.gateway.app.admission import admit
from apps.gateway.app.paths import PROJECT_DIR
from apps.gateway.app.stt import transcribe_station_audio
from apps.gateway.app.providers import (
    heavy_services,
    provider_for_catalog_model,
    registry,
    service_profiles,
)

CATALOG_PATH = Path(
    os.getenv("AI_STATION_MODEL_CATALOG", str(PROJECT_DIR / "config/model-catalog.json"))
)

COMPOSE_HELPER = PROJECT_DIR / "scripts" / "compose-ai-station.sh"
COMPOSE_BASE = (
    [str(COMPOSE_HELPER)]
    if COMPOSE_HELPER.is_file()
    else [
        "docker",
        "compose",
        "--project-name",
        os.getenv("COMPOSE_PROJECT_NAME", "ai-station"),
        "--env-file",
        str(PROJECT_DIR / ".env"),
    ]
)

MODEL_LOCK = asyncio.Lock()
QUEUE: list[dict[str, Any]] = []
ACTIVE_MODEL_ID: str | None = None
GATEWAY_VERSION = "0.6.0"

app = FastAPI(title="AI Station Gateway", version=GATEWAY_VERSION)


def emit_contract_telemetry(event: str, **fields: Any) -> None:
    """Emit content-free OpenAI contract telemetry for client debugging."""
    print(
        json.dumps({"event": event, **fields}, ensure_ascii=True, sort_keys=True),
        file=sys.stderr,
        flush=True,
    )


def response_shape(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__}
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    return {
        "content_chars": len(content) if isinstance(content, str) else 0,
        "finish_reason": choice.get("finish_reason"),
        "tool_calls": len(message.get("tool_calls") or []),
    }


def safe_upstream_error(error_bytes: bytes, status_code: int) -> tuple[str, str]:
    """Return a useful client error and a content-free telemetry category."""
    message = ""
    category = f"http_{status_code}"
    try:
        payload = json.loads(error_bytes)
        detail = payload.get("error") or payload.get("detail")
        if isinstance(detail, dict):
            message = str(detail.get("message") or "")
            declared = detail.get("type") or detail.get("code")
            if declared:
                category = str(declared)[:80]
        elif detail is not None:
            message = str(detail)
    except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
        pass

    if "exceeds the available context size" in message:
        return message[:300], "context_window_exceeded"
    return f"Local model returned HTTP {status_code}.", category


def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def cached_catalog() -> dict[str, Any]:
    return load_catalog()


def catalog_models() -> list[dict[str, Any]]:
    return cached_catalog().get("models", [])


def normalize_model_id(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[-1]
    return model_id


def public_model_id(model: dict[str, Any]) -> str:
    return str(model.get("public_model_id") or model["id"])


def valid_public_model_ids() -> list[str]:
    return [public_model_id(model) for model in selectable_models()]


def selectable_models() -> list[dict[str, Any]]:
    return [
        m
        for m in catalog_models()
        if m.get("enabled") is True and m.get("kind") in {"chat", "vision"}
    ]


def model_matches(model: dict[str, Any], requested_id: str) -> bool:
    return requested_id in {
        public_model_id(model),
        str(model.get("id")),
        str(model.get("alias") or ""),
    }


def get_model(model_id: str) -> dict[str, Any]:
    requested_id = normalize_model_id(model_id)
    for model in selectable_models():
        if model_matches(model, requested_id):
            return model
    raise HTTPException(
        status_code=404,
        detail={
            "message": f"Unknown model '{requested_id}'.",
            "valid_model_names": valid_public_model_ids(),
        },
    )


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


def profile_args_for_services(services: list[str]) -> list[str]:
    args: list[str] = []
    seen: set[str] = set()
    profiles = service_profiles()
    for service in services:
        profile = profiles.get(service)
        if profile and profile not in seen:
            args.extend(["--profile", profile])
            seen.add(profile)
    return args


async def stop_other_heavy(target_service: str) -> None:
    to_stop = [s for s in heavy_services() if s != target_service]
    if not to_stop:
        return
    await compose([*profile_args_for_services(to_stop), "stop", *to_stop], timeout=240)


async def wait_ready(model: dict[str, Any], attempts: int = 480) -> None:
    url = f"{model['base_url']}/models"

    async with httpx.AsyncClient(timeout=5) as client:
        last_error = None
        for _ in range(attempts):
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}: {response.text[:500]}"
            except Exception as exc:
                last_error = repr(exc)
            await asyncio.sleep(2)

    raise HTTPException(
        status_code=503,
        detail={
            "stage": "wait_ready",
            "model": model["id"],
            "service": model.get("service"),
            "url": url,
            "last_error": last_error,
        },
    )


def evaluate_admission(model: dict[str, Any]) -> dict[str, Any]:
    provider = provider_for_catalog_model(model)
    policy = (registry().get("admission") or {})
    decision = admit(provider["id"])
    payload = decision.to_dict()
    payload["enforce"] = bool(policy.get("enforce", True))
    if decision.decision == "REJECT" and payload["enforce"]:
        raise HTTPException(
            status_code=503,
            detail={
                "stage": "admission",
                "decision": payload,
            },
        )
    if decision.decision == "FALLBACK" and payload["enforce"]:
        raise HTTPException(
            status_code=503,
            detail={
                "stage": "admission",
                "decision": payload,
                "message": "Provider rejected; use fallback explicitly",
            },
        )
    return payload


async def start_runtime(model: dict[str, Any]) -> dict[str, Any]:
    global ACTIVE_MODEL_ID

    service = model.get("service")
    if not service:
        raise HTTPException(status_code=400, detail=f"Model has no runtime service: {model['id']}")

    admission = evaluate_admission(model)

    if model.get("heavy"):
        await stop_other_heavy(service)

    result = await compose(
        [*profile_args_for_services([service]), "up", "-d", service],
        timeout=300,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail={
                "stage": "start_runtime",
                "model": model["id"],
                "service": service,
                "stdout": result.stdout[-4000:],
                "stderr": result.stderr[-4000:],
                "admission": admission,
            },
        )

    await wait_ready(model)

    if model.get("heavy"):
        ACTIVE_MODEL_ID = public_model_id(model)

    return admission


def merge_system_prefix(prefix: str, content: Any) -> Any:
    """Prepend prefix text to an existing system message's content.

    Handles both plain string content and OpenAI-style multi-part list
    content defensively, always returning a shape consistent with the
    original content's type.
    """
    if isinstance(content, list):
        return [{"type": "text", "text": prefix}] + list(content)
    if content is None:
        return prefix
    return f"{prefix}\n{content}"


def rewrite_messages(model: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    body = dict(body)
    body["model"] = model["backend_model"]

    prefix = model.get("default_system_prefix") or ""
    if prefix:
        messages = list(body.get("messages", []))
        first = messages[0] if messages else None
        if isinstance(first, dict) and first.get("role") == "system":
            # llama.cpp's Jinja chat template requires a single leading
            # system message; merge instead of inserting a second one
            # (see docs/adr/ADR-009-opencode-local-client.md).
            merged = dict(first)
            merged["content"] = merge_system_prefix(prefix, first.get("content"))
            messages[0] = merged
        else:
            messages.insert(0, {"role": "system", "content": prefix})
        body["messages"] = messages

    return body


def responses_content_to_chat(content: Any) -> Any:
    if isinstance(content, str) or content is None:
        return content or ""
    if not isinstance(content, list):
        return str(content)
    parts: list[dict[str, Any]] = []
    for part in content:
        if isinstance(part, str):
            parts.append({"type": "text", "text": part})
            continue
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"}:
            parts.append({"type": "text", "text": str(part.get("text") or "")})
        elif part_type in {"input_image", "image_url"}:
            image_url = part.get("image_url") or part.get("url")
            if isinstance(image_url, str):
                image_url = {"url": image_url}
            if isinstance(image_url, dict):
                parts.append({"type": "image_url", "image_url": image_url})
    if len(parts) == 1 and parts[0].get("type") == "text":
        return parts[0]["text"]
    return parts


def responses_input_to_messages(body: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    instructions = body.get("instructions")
    if instructions:
        messages.append(
            {
                "role": "system",
                "content": responses_content_to_chat(instructions),
            }
        )

    items = body.get("input", "")
    if isinstance(items, str):
        messages.append({"role": "user", "content": items})
        return messages
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="Responses input must be text or a list")

    for item in items:
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        role = item.get("role")
        if role in {"system", "developer", "user", "assistant"}:
            messages.append(
                {
                    "role": "system" if role == "developer" else role,
                    "content": responses_content_to_chat(item.get("content")),
                }
            )
        elif item_type == "function_call":
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": item.get("call_id") or item.get("id") or str(uuid.uuid4()),
                            "type": "function",
                            "function": {
                                "name": item.get("name"),
                                "arguments": item.get("arguments") or "{}",
                            },
                        }
                    ],
                }
            )
        elif item_type == "function_call_output":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.get("call_id") or item.get("id"),
                    "content": responses_content_to_chat(item.get("output")),
                }
            )
    return messages


def responses_tools_to_chat(tools: Any) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    if not isinstance(tools, list):
        return converted
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        if isinstance(tool.get("function"), dict):
            converted.append(tool)
            continue
        function = {
            "name": tool.get("name"),
            "description": tool.get("description") or "",
            "parameters": tool.get("parameters") or {"type": "object", "properties": {}},
        }
        if "strict" in tool:
            function["strict"] = bool(tool["strict"])
        converted.append({"type": "function", "function": function})
    return converted


def responses_to_chat_body(body: dict[str, Any]) -> dict[str, Any]:
    chat: dict[str, Any] = {
        "model": body.get("model"),
        "messages": responses_input_to_messages(body),
        "stream": False,
    }
    for key in ("temperature", "top_p", "parallel_tool_calls", "seed", "user"):
        if key in body:
            chat[key] = body[key]
    if "max_output_tokens" in body:
        chat["max_tokens"] = body["max_output_tokens"]
    elif "max_tokens" in body:
        chat["max_tokens"] = body["max_tokens"]
    tools = responses_tools_to_chat(body.get("tools"))
    if tools:
        chat["tools"] = tools
    tool_choice = body.get("tool_choice")
    if isinstance(tool_choice, dict) and tool_choice.get("type") == "function":
        chat["tool_choice"] = {
            "type": "function",
            "function": {"name": tool_choice.get("name")},
        }
    elif isinstance(tool_choice, str) and tool_choice in {"auto", "none", "required"}:
        chat["tool_choice"] = tool_choice
    text_format = (body.get("text") or {}).get("format")
    if isinstance(text_format, dict) and text_format.get("type") in {
        "json_object",
        "json_schema",
    }:
        chat["response_format"] = text_format
    return chat


def chat_to_responses(
    payload: dict[str, Any], requested_model: str, response_id: str | None = None
) -> dict[str, Any]:
    response_id = response_id or f"resp_{uuid.uuid4().hex}"
    choice = (payload.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    output: list[dict[str, Any]] = []
    content = message.get("content")
    if not content_is_empty(content):
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        output.append(
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": content, "annotations": []}
                ],
            }
        )
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)
        output.append(
            {
                "id": f"fc_{uuid.uuid4().hex}",
                "type": "function_call",
                "status": "completed",
                "call_id": call.get("id") or f"call_{uuid.uuid4().hex}",
                "name": function.get("name"),
                "arguments": arguments,
            }
        )

    usage = payload.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    created_at = int(payload.get("created") or time.time())
    return {
        "id": response_id,
        "object": "response",
        "created_at": created_at,
        "completed_at": int(time.time()),
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "model": requested_model,
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "temperature": None,
        "top_p": None,
        "usage": {
            "input_tokens": input_tokens,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": output_tokens,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": int(usage.get("total_tokens") or input_tokens + output_tokens),
        },
    }


def content_is_empty(content: Any) -> bool:
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict):
                texts.append(str(part.get("text") or ""))
        return not "".join(texts).strip()
    return False


def flatten_reasoning_into_content(payload: Any) -> Any:
    """Copy reasoning_content into content when content is empty.

    OpenCode agent loops need message.content or tool_calls. Some llama.cpp
    reasoning paths fill only reasoning_content. Preserve tool_calls.
    """
    if not isinstance(payload, dict):
        return payload
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return payload
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        for key in ("message", "delta"):
            block = choice.get(key)
            if not isinstance(block, dict):
                continue
            reasoning = block.get("reasoning_content")
            if (
                content_is_empty(block.get("content"))
                and isinstance(reasoning, str)
                and reasoning.strip()
            ):
                block["content"] = reasoning
    return payload


def flatten_sse_line(line: bytes) -> bytes:
    raw = line.rstrip(b"\r\n")
    suffix = line[len(raw) :]
    if not raw.startswith(b"data:"):
        return line
    data = raw[5:].lstrip()
    if data == b"[DONE]" or not data:
        return line
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return line
    flatten_reasoning_into_content(payload)
    return b"data: " + json.dumps(payload, ensure_ascii=False).encode("utf-8") + suffix


async def iter_flattened_sse(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    buffer = bytearray()
    async for chunk in chunks:
        buffer.extend(chunk)
        while True:
            idx = buffer.find(b"\n")
            if idx < 0:
                break
            line = bytes(buffer[: idx + 1])
            del buffer[: idx + 1]
            yield flatten_sse_line(line)
    if buffer:
        yield flatten_sse_line(bytes(buffer))


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": GATEWAY_VERSION,
        "active_model_id": ACTIVE_MODEL_ID,
        "queue_length": len(QUEUE),
        "catalog_path": str(CATALOG_PATH),
        "providers": list((registry().get("providers") or {}).keys()),
        "models": valid_public_model_ids(),
    }


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": public_model_id(m),
                "name": m.get("display_name"),
                "object": "model",
                "created": 0,
                "owned_by": "ai-station",
                "root": public_model_id(m),
                "canonical_id": public_model_id(m),
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


@app.get("/v1/providers")
async def providers() -> dict[str, Any]:
    return {
        "admission": registry().get("admission") or {},
        "providers": registry().get("providers") or {},
    }


@app.post("/v1/admission/dry-run")
async def admission_dry_run(request: Request) -> dict[str, Any]:
    body = await request.json()
    provider_id = body.get("provider_id") or body.get("model")
    if not provider_id:
        raise HTTPException(status_code=400, detail="provider_id or model required")
    context = body.get("context")
    decision = admit(str(provider_id), context=context)
    return decision.to_dict()


@app.post("/v1/audio/transcriptions")
async def audio_transcriptions(request: Request) -> dict[str, Any]:
    audio = await request.body()
    language = request.query_params.get("language")
    want_timestamps = request.query_params.get("timestamps") in {"1", "true", "yes"}
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio body")
    result = await asyncio.to_thread(
        transcribe_station_audio,
        audio,
        language=language,
        want_timestamps=want_timestamps,
    )
    payload: dict[str, Any] = {
        "text": result.text,
        "engine": result.engine,
        "fallback_used": result.fallback_used,
    }
    if result.language:
        payload["language"] = result.language
    if result.timestamps:
        payload["segments"] = result.timestamps
    return payload


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
        "model": public_model_id(model),
        "state": "queued",
        "created_at": time.time(),
    }
    QUEUE.append(item)

    if bool(raw_body.get("stream", False)):
        return StreamingResponse(
            stream_proxy(request, model, body, item, requested),
            media_type="text/event-stream",
        )

    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            admission = await start_runtime(model)
            item["state"] = "running"
            item["admission"] = admission

            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    f"{model['base_url']}/chat/completions",
                    json=body,
                )
                try:
                    content = response.json()
                except Exception:
                    content = {"error": response.text}
                if isinstance(content, dict):
                    flatten_reasoning_into_content(content)
                emit_contract_telemetry(
                    "chat_completion",
                    model=requested,
                    stream=False,
                    messages=len(raw_body.get("messages") or []),
                    tools=len(raw_body.get("tools") or []),
                    **response_shape(content),
                )
                return JSONResponse(content=content, status_code=response.status_code)
    finally:
        if item in QUEUE:
            QUEUE.remove(item)


async def stream_proxy(
    request: Request,
    model: dict[str, Any],
    body: dict[str, Any],
    item: dict[str, Any],
    requested_model: str,
) -> AsyncIterator[bytes]:
    content_chars = 0
    tool_call_events = 0
    finish_reason: str | None = None
    upstream_status: int | None = None
    upstream_content_type: str | None = None
    upstream_error_type: str | None = None
    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            yield b": AI Station is preparing the selected local model\n\n"
            admission = await start_runtime(model)
            item["state"] = "running"
            item["admission"] = admission

            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST",
                    f"{model['base_url']}/chat/completions",
                    json=body,
                ) as response:
                    upstream_status = response.status_code
                    upstream_content_type = response.headers.get("content-type")
                    if response.status_code >= 400:
                        error_bytes = await response.aread()
                        client_error, upstream_error_type = safe_upstream_error(
                            error_bytes, response.status_code
                        )
                        error_event = json.dumps(
                            {
                                "error": {
                                    "message": client_error,
                                    "type": "upstream_model_error",
                                }
                            }
                        )
                        yield f"data: {error_event}\n\ndata: [DONE]\n\n".encode()
                        return
                    async for chunk in iter_flattened_sse(response.aiter_bytes()):
                        if await request.is_disconnected():
                            break
                        raw = chunk.strip()
                        if raw.startswith(b"data:") and raw[5:].strip() not in {
                            b"",
                            b"[DONE]",
                        }:
                            try:
                                event = json.loads(raw[5:].strip())
                                choice = (event.get("choices") or [{}])[0]
                                delta = choice.get("delta") or {}
                                text = delta.get("content")
                                if isinstance(text, str):
                                    content_chars += len(text)
                                tool_call_events += len(delta.get("tool_calls") or [])
                                if choice.get("finish_reason") is not None:
                                    finish_reason = str(choice["finish_reason"])
                            except (AttributeError, json.JSONDecodeError):
                                pass
                        yield chunk
    except Exception as exc:
        payload = json.dumps(
            {
                "error": {
                    "message": str(exc),
                    "type": "ai_station_gateway_error",
                }
            },
            ensure_ascii=False,
        )
        yield f"data: {payload}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"
    finally:
        emit_contract_telemetry(
            "chat_completion",
            model=requested_model,
            stream=True,
            messages=len(body.get("messages") or []),
            tools=len(body.get("tools") or []),
            content_chars=content_chars,
            tool_call_events=tool_call_events,
            finish_reason=finish_reason,
            upstream_status=upstream_status,
            upstream_content_type=upstream_content_type,
            upstream_error_type=upstream_error_type,
            request_keys=sorted(body),
            tool_choice_type=type(body.get("tool_choice")).__name__,
            message_roles=[
                message.get("role")
                for message in body.get("messages") or []
                if isinstance(message, dict)
            ],
        )
        if item in QUEUE:
            QUEUE.remove(item)


def responses_sse_event(event_type: str, payload: dict[str, Any]) -> bytes:
    return (
        f"event: {event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    ).encode("utf-8")


async def responses_stream_proxy(
    request: Request,
    model: dict[str, Any],
    chat_body: dict[str, Any],
    item: dict[str, Any],
    requested_model: str,
) -> AsyncIterator[bytes]:
    response_id = f"resp_{uuid.uuid4().hex}"
    sequence = 0
    created = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "in_progress",
        "model": requested_model,
        "output": [],
    }
    yield responses_sse_event(
        "response.created",
        {"type": "response.created", "response": created, "sequence_number": sequence},
    )
    sequence += 1
    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            admission = await start_runtime(model)
            item["state"] = "running"
            item["admission"] = admission
            async with httpx.AsyncClient(timeout=None) as client:
                upstream = await client.post(
                    f"{model['base_url']}/chat/completions",
                    json=chat_body,
                )
                payload = upstream.json()
                if upstream.status_code >= 400:
                    raise RuntimeError(str(payload)[:600])
                flatten_reasoning_into_content(payload)
                completed = chat_to_responses(payload, requested_model, response_id)

        for output_index, output_item in enumerate(completed["output"]):
            if await request.is_disconnected():
                return
            in_progress = dict(output_item)
            in_progress["status"] = "in_progress"
            yield responses_sse_event(
                "response.output_item.added",
                {
                    "type": "response.output_item.added",
                    "output_index": output_index,
                    "item": in_progress,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
            if output_item["type"] == "message":
                part = output_item["content"][0]
                yield responses_sse_event(
                    "response.content_part.added",
                    {
                        "type": "response.content_part.added",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "part": {"type": "output_text", "text": "", "annotations": []},
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "delta": part["text"],
                        "logprobs": [],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.output_text.done",
                    {
                        "type": "response.output_text.done",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "text": part["text"],
                        "logprobs": [],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.content_part.done",
                    {
                        "type": "response.content_part.done",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "content_index": 0,
                        "part": part,
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
            elif output_item["type"] == "function_call":
                yield responses_sse_event(
                    "response.function_call_arguments.delta",
                    {
                        "type": "response.function_call_arguments.delta",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "delta": output_item["arguments"],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
                yield responses_sse_event(
                    "response.function_call_arguments.done",
                    {
                        "type": "response.function_call_arguments.done",
                        "item_id": output_item["id"],
                        "output_index": output_index,
                        "name": output_item["name"],
                        "arguments": output_item["arguments"],
                        "sequence_number": sequence,
                    },
                )
                sequence += 1
            yield responses_sse_event(
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "output_index": output_index,
                    "item": output_item,
                    "sequence_number": sequence,
                },
            )
            sequence += 1
        yield responses_sse_event(
            "response.completed",
            {
                "type": "response.completed",
                "response": completed,
                "sequence_number": sequence,
            },
        )
    except Exception as exc:
        failed = dict(created)
        failed["status"] = "failed"
        failed["error"] = {
            "code": "ai_station_gateway_error",
            "message": str(exc),
        }
        yield responses_sse_event(
            "response.failed",
            {
                "type": "response.failed",
                "response": failed,
                "sequence_number": sequence,
            },
        )
    finally:
        if item in QUEUE:
            QUEUE.remove(item)


@app.post("/v1/responses")
async def responses(request: Request):
    raw_body = await request.json()
    requested = raw_body.get("model")
    if not requested:
        raise HTTPException(status_code=400, detail="Missing model")

    model = get_model(str(requested))
    chat_body = rewrite_messages(model, responses_to_chat_body(raw_body))
    item = {
        "id": str(uuid.uuid4()),
        "model": public_model_id(model),
        "endpoint": "responses",
        "state": "queued",
        "created_at": time.time(),
    }
    QUEUE.append(item)

    if bool(raw_body.get("stream", False)):
        return StreamingResponse(
            responses_stream_proxy(request, model, chat_body, item, str(requested)),
            media_type="text/event-stream",
        )

    try:
        async with MODEL_LOCK:
            item["state"] = "starting_model"
            admission = await start_runtime(model)
            item["state"] = "running"
            item["admission"] = admission
            async with httpx.AsyncClient(timeout=None) as client:
                upstream = await client.post(
                    f"{model['base_url']}/chat/completions",
                    json=chat_body,
                )
                try:
                    payload = upstream.json()
                except Exception:
                    payload = {"error": upstream.text}
                if upstream.status_code >= 400 or not isinstance(payload, dict):
                    return JSONResponse(content=payload, status_code=upstream.status_code)
                flatten_reasoning_into_content(payload)
                converted = chat_to_responses(payload, str(requested))
                return JSONResponse(content=converted, status_code=upstream.status_code)
    finally:
        if item in QUEUE:
            QUEUE.remove(item)
