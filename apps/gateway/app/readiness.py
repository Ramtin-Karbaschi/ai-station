"""Provider readiness polling, isolated from lifecycle mutation."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import HTTPException


async def wait_ready(model: dict[str, Any], attempts: int = 480) -> None:
    """Wait for the provider's OpenAI ``/models`` endpoint to return 200."""
    attempts = int(model.get("readiness_attempts", attempts))
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
