import json
import os
from pathlib import Path
from typing import Any

import asyncpg
from arq.connections import RedisSettings


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


async def startup(ctx: dict[str, Any]) -> None:
    ctx["db"] = await asyncpg.connect(**db_config())


async def shutdown(ctx: dict[str, Any]) -> None:
    db = ctx.get("db")
    if db:
        await db.close()


async def smoke_job(ctx: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    db = ctx["db"]
    await db.execute(
        """
        INSERT INTO ai_station_audit_events
        (event_type, actor_id, entity_type, entity_id, payload)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        """,
        "smoke_job_completed",
        "system",
        "job",
        payload.get("source", "api"),
        json.dumps({"result": "AI Station worker path is working", "input": payload}),
    )
    return {"ok": True, "message": "AI Station worker path is working", "payload": payload}


class WorkerSettings:
    functions = [smoke_job]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", "6379")),
    )
