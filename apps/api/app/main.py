import os
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import redis.asyncio as redis
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel


def read_secret(path: str | None, fallback: str = "") -> str:
    if not path:
        return fallback
    p = Path(path)
    if p.exists():
        return p.read_text().strip()
    return fallback


def db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "ai_station"),
        "password": read_secret(os.getenv("POSTGRES_PASSWORD_FILE")),
        "database": os.getenv("POSTGRES_DB", "ai_station"),
    }


class SmokeJobRequest(BaseModel):
    source: str = "api"
    note: str = "AI Station smoke job"


app = FastAPI(title="AI Station API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:8088",
        "http://localhost:8088",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

redis_pool: redis.Redis | None = None
arq_pool: Any = None


@app.on_event("startup")
async def startup() -> None:
    global redis_pool, arq_pool
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))

    redis_pool = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
    arq_pool = await create_pool(RedisSettings(host=redis_host, port=redis_port))


@app.on_event("shutdown")
async def shutdown() -> None:
    if redis_pool:
        await redis_pool.aclose()
    if arq_pool:
        await arq_pool.close()


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "AI Station API",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    checks: dict[str, Any] = {}

    try:
        conn = await asyncpg.connect(**db_config())
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        checks["postgres"] = {"ok": True, "version": version}
    except Exception as exc:
        checks["postgres"] = {"ok": False, "error": str(exc)}

    try:
        assert redis_pool is not None
        pong = await redis_pool.ping()
        checks["redis"] = {"ok": bool(pong)}
    except Exception as exc:
        checks["redis"] = {"ok": False, "error": str(exc)}

    overall = all(v.get("ok") for v in checks.values())
    return {"ok": overall, "checks": checks}


@app.get("/health/llm")
async def health_llm() -> dict[str, Any]:
    base_url = os.getenv("LLM_BASE_URL", "http://llm:8081/v1")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base_url}/models")
            return {"ok": r.status_code < 500, "status_code": r.status_code, "body": r.text[:1000]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/jobs/smoke")
async def enqueue_smoke_job(payload: SmokeJobRequest) -> dict[str, Any]:
    if arq_pool is None:
        raise HTTPException(status_code=503, detail="Queue is not ready")

    job = await arq_pool.enqueue_job("smoke_job", payload.model_dump())
    return {
        "ok": True,
        "job_id": job.job_id if job else None,
        "queued": bool(job),
    }


@app.post("/llm/smoke")
async def llm_smoke() -> dict[str, Any]:
    base_url = os.getenv("LLM_BASE_URL", "http://llm:8081/v1")

    request_body = {
        "model": "ai-station-local",
        "messages": [
            {
                "role": "system",
                "content": "You are a local AI Station diagnostic assistant. Answer briefly.",
            },
            {
                "role": "user",
                "content": "Say: AI Station LLM path is working.",
            },
        ],
        "temperature": 0,
        "max_tokens": 64,
    }

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(f"{base_url}/chat/completions", json=request_body)
            return {
                "ok": r.status_code == 200,
                "status_code": r.status_code,
                "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text,
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
