#!/usr/bin/env python3
"""Qwen3-TTS weight verify. Does not start a GPU synthesizer (ADR-037)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

TTS_IDS = (
    "studio-qwen3-tts-1.7b-customvoice",
    "studio-qwen3-tts-1.7b-voicedesign",
    "studio-qwen3-tts-tokenizer",
)
MODEL_SNAPSHOT_FILES = (
    "config.json",
    "generation_config.json",
    "merges.txt",
    "preprocessor_config.json",
    "tokenizer_config.json",
    "vocab.json",
)
SPEECH_TOKENIZER_SNAPSHOT_FILES = (
    "config.json",
    "configuration.json",
    # The official Qwen3-TTS loader resolves tokenizer weights relative to
    # each model's nested speech_tokenizer directory.
    "model.safetensors",
    "preprocessor_config.json",
)


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("model manifest is not an object")
    return payload


def tts_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    models = manifest.get("models")
    if not isinstance(models, list):
        return []
    wanted = set(TTS_IDS)
    rows: list[dict[str, Any]] = []
    for item in models:
        if isinstance(item, dict) and item.get("id") in wanted:
            rows.append(item)
    return rows


def snapshot_complete(model_dir: Path) -> bool:
    return all((model_dir / name).is_file() for name in MODEL_SNAPSHOT_FILES) and all(
        (model_dir / "speech_tokenizer" / name).is_file()
        for name in SPEECH_TOKENIZER_SNAPSHOT_FILES
    )


def snapshot_missing(
    data_root: Path, *, tokenizer_sha256: str | None = None
) -> list[str]:
    missing: list[str] = []
    for model_name in (
        "qwen3-tts-12hz-1.7b-customvoice",
        "qwen3-tts-12hz-1.7b-voicedesign",
    ):
        model_dir = data_root / "models/tts" / model_name
        missing.extend(
            str(Path(model_name) / name)
            for name in MODEL_SNAPSHOT_FILES
            if not (model_dir / name).is_file()
        )
        missing.extend(
            str(Path(model_name) / "speech_tokenizer" / name)
            for name in SPEECH_TOKENIZER_SNAPSHOT_FILES
            if not (model_dir / "speech_tokenizer" / name).is_file()
        )
        nested_tokenizer = model_dir / "speech_tokenizer" / "model.safetensors"
        source_tokenizer = data_root / "models/tts/qwen3-tts-tokenizer/model.safetensors"
        if (
            tokenizer_sha256
            and nested_tokenizer.is_file()
            and source_tokenizer.is_file()
            and not nested_tokenizer.samefile(source_tokenizer)
            and sha256_file(nested_tokenizer) != tokenizer_sha256
        ):
            missing.append(
                str(Path(model_name) / "speech_tokenizer/model.safetensors.sha256_mismatch")
            )
    tokenizer_dir = data_root / "models/tts/qwen3-tts-tokenizer"
    if not (tokenizer_dir / "model.safetensors").is_file():
        missing.append("qwen3-tts-tokenizer/model.safetensors")
    return missing


def verify_weights(
    *,
    data_root: Path,
    manifest: Mapping[str, Any],
    hash_fn=sha256_file,
) -> dict[str, Any]:
    rows = tts_rows(manifest)
    files: list[dict[str, Any]] = []
    ok = True
    for row in rows:
        dest = data_root / str(row.get("destination") or "")
        expected = str(row.get("sha256") or "")
        present = dest.is_file()
        digest = hash_fn(dest) if present else ""
        match = bool(present and expected and digest == expected)
        if not match:
            ok = False
        files.append(
            {
                "id": row.get("id"),
                "path": str(dest),
                "present": present,
                "sha256_match": match,
                "bytes": dest.stat().st_size if present else 0,
            }
        )
    missing_ids = [item for item in TTS_IDS if item not in {row.get("id") for row in rows}]
    if missing_ids:
        ok = False
    custom = data_root / "models/tts/qwen3-tts-12hz-1.7b-customvoice"
    tokenizer_row = next(
        (row for row in rows if row.get("id") == "studio-qwen3-tts-tokenizer"),
        {},
    )
    missing_snapshot_files = snapshot_missing(
        data_root, tokenizer_sha256=str(tokenizer_row.get("sha256") or "") or None
    )
    complete = not missing_snapshot_files
    return {
        "ok": ok and not missing_ids,
        "engine": "qwen3-tts-12hz-1.7b-customvoice",
        "weights_verified": ok and not missing_ids,
        "snapshot_complete": complete,
        "missing_snapshot_files": missing_snapshot_files,
        "inference": "not_run",
        "speech_http": 503,
        "second_heavy_gpu": False,
        "missing_manifest_ids": missing_ids,
        "files": files,
        "blocker": (
            None
            if complete and ok
            else (
                "HF snapshot is weights-only (no config.json). GPU TTS is not "
                "started beside chat (ADR-037)."
            )
        ),
    }


def smoke_report(
    *,
    project_root: Path,
    data_root: Path,
    hash_files: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    manifest_path = project_root / "config" / "model-manifest.json"
    manifest = load_manifest(manifest_path)
    if hash_files:
        body = verify_weights(data_root=data_root, manifest=manifest)
    else:
        rows = tts_rows(manifest)
        body = {
            "ok": True,
            "dry_run": True,
            "engine": "qwen3-tts-12hz-1.7b-customvoice",
            "inference": "not_run",
            "speech_http": 503,
            "second_heavy_gpu": False,
            "files": [
                {
                    "id": row.get("id"),
                    "path": str(data_root / str(row.get("destination") or "")),
                    "expected_sha256": row.get("sha256"),
                    "expected_bytes": row.get("size_bytes"),
                }
                for row in rows
            ],
        }
    moment = now or datetime.now(timezone.utc)
    body["tested_at"] = moment.isoformat()
    body["cloud"] = False
    return body


def write_report(report: Mapping[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(report), indent=2) + "\n", encoding="utf-8")
    return path
