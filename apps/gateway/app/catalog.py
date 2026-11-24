"""Runtime model catalog and public model identity helpers.

This module owns catalog I/O and pure selection rules.  HTTP error shaping and
lifecycle admission remain in ``main`` so catalog policy cannot acquire
transport or Compose side effects.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from apps.gateway.app.paths import PROJECT_DIR

CATALOG_PATH = Path(
    os.getenv("AI_STATION_MODEL_CATALOG", str(PROJECT_DIR / "config/model-catalog.json"))
)


def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("r", encoding="utf-8") as stream:
        return json.load(stream)


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


def selectable_models() -> list[dict[str, Any]]:
    return [
        model
        for model in catalog_models()
        if model.get("enabled") is True and model.get("kind") in {"chat", "vision"}
    ]


def valid_public_model_ids() -> list[str]:
    return [public_model_id(model) for model in selectable_models()]


def model_matches(model: dict[str, Any], requested_id: str) -> bool:
    return requested_id in {
        public_model_id(model),
        str(model.get("id")),
        str(model.get("alias") or ""),
    }
