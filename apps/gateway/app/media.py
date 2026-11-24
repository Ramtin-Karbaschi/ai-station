"""Protect in-flight ComfyUI jobs during inference provider switches."""
from typing import Any

import httpx
from fastapi import HTTPException


async def assert_media_idle(admission: dict[str, Any], providers: dict[str, Any]) -> None:
    for provider_id in admission.get("active_heavy", []):
        provider = providers.get(provider_id, {})
        if provider.get("engine") != "comfyui":
            continue
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(provider["endpoint"].rstrip("/") + "/queue")
                response.raise_for_status()
                queue = response.json()
            if not isinstance(queue, dict) or not all(isinstance(queue.get(k), list)
                                                      for k in ("queue_running", "queue_pending")):
                raise ValueError("invalid media queue response")
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise HTTPException(503, "Cannot verify the media queue; GPU switch deferred") from exc
        if queue["queue_running"] or queue["queue_pending"]:
            raise HTTPException(503, "Media generation is busy; retry after the ComfyUI queue completes")
