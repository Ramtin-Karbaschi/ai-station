"""Provider registry loader for the AI Station gateway."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.gateway.app.admission import get_provider, load_providers

PROJECT_DIR = Path(os.getenv("AI_STATION_PROJECT_DIR", "/opt/ai-station"))
PROVIDERS_PATH = Path(
    os.getenv("AI_STATION_PROVIDERS", str(PROJECT_DIR / "config/providers.yaml"))
)


@lru_cache(maxsize=1)
def registry() -> dict[str, Any]:
    return load_providers(PROVIDERS_PATH)


def reload_registry() -> dict[str, Any]:
    registry.cache_clear()
    return registry()


def heavy_services() -> list[str]:
    services: list[str] = []
    for provider in (registry().get("providers") or {}).values():
        if provider.get("heavy") and provider.get("service"):
            services.append(provider["service"])
    return services


def service_profiles() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for provider in (registry().get("providers") or {}).values():
        service = provider.get("service")
        profile = provider.get("profile")
        if service and profile and profile != "default":
            mapping[service] = profile
    return mapping


def provider_for_catalog_model(model: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        model.get("id"),
        model.get("alias"),
        model.get("service"),
        model.get("profile"),
    ]
    last_error: Exception | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return get_provider(registry(), str(candidate))
        except KeyError as exc:
            last_error = exc
    raise KeyError(
        f"No provider registered for model {model.get('id')}"
    ) from last_error
