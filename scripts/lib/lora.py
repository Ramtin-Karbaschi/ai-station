#!/usr/bin/env python3
"""Optional LoRA pipeline (ADR-035). No in-process GPU trainer."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_ROWS = 200
MAX_BYTES = 262144
ALLOWED_BASES = frozenset({"qwen38-27b-q4", "ornith-1.5-35b-q4"})
GGUF_MAGIC = b"GGUF"
SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._\-]{12,}|api[_-]?key\s*=)",
    re.IGNORECASE,
)
TEXT_KEYS = ("instruction", "output", "prompt", "response", "input")


class LoraError(RuntimeError):
    """LoRA pipeline failed."""


def project_root() -> Path:
    configured = os.environ.get("AI_STATION_PROJECT_DIR")
    return Path(configured).resolve() if configured else Path(__file__).resolve().parents[2]


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def runtime_dir() -> Path:
    override = os.environ.get("AI_STATION_LORA_DIR")
    if override:
        return Path(override)
    return data_root() / "runtime" / "lora"


def example_dataset() -> Path:
    return project_root() / "config/lora/station-ops.example.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise LoraError(f"dataset not found: {path}")
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise LoraError(f"dataset exceeds {MAX_BYTES} bytes")
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except ValueError as exc:
            raise LoraError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(item, dict):
            raise LoraError(f"row {line_number} must be a JSON object")
        rows.append(item)
    if not rows:
        raise LoraError("dataset has no rows")
    if len(rows) > MAX_ROWS:
        raise LoraError(f"dataset has {len(rows)} rows; max is {MAX_ROWS}")
    return rows


def validate_dataset(path: Path) -> dict[str, Any]:
    rows = load_jsonl(path)
    for index, row in enumerate(rows, 1):
        has_instruction = bool(str(row.get("instruction") or row.get("prompt") or "").strip())
        has_output = bool(str(row.get("output") or row.get("response") or "").strip())
        if not has_instruction or not has_output:
            raise LoraError(
                f"row {index} needs instruction/prompt and output/response"
            )
        blob = " ".join(str(row.get(key) or "") for key in TEXT_KEYS)
        if SECRET_RE.search(blob):
            raise LoraError(f"row {index} looks like it contains a secret")
    return {
        "ok": True,
        "path": str(path),
        "rows": len(rows),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }


def plan(
    dataset: Path,
    *,
    base: str,
    adapter_id: str,
) -> dict[str, Any]:
    if base not in ALLOWED_BASES:
        raise LoraError(f"unsupported base {base}; allowed: {sorted(ALLOWED_BASES)}")
    report = validate_dataset(dataset)
    adapter_name = f"{adapter_id}.gguf"
    return {
        "status": "planned",
        "train_implemented": False,
        "classification": "optional_profile",
        "base": base,
        "adapter_id": adapter_id,
        "dataset": report,
        "gpu": "exclusive; stop the active heavy profile before any off-box training",
        "steps": [
            "validate dataset",
            "train PEFT off-box (not implemented on the station)",
            "convert adapter to GGUF",
            "ai lora register --adapter PATH --base BASE --id ID",
            "ai lora apply --id ID --dry-run",
            "restart the matching heavy profile if apply is confirmed",
        ],
        "llama_cpp_args": ["--lora", f"/lora/{adapter_name}"],
        "planned_at": _utc_now(),
    }


def is_gguf(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("rb") as handle:
        return handle.read(4) == GGUF_MAGIC


def registry_path() -> Path:
    return runtime_dir() / "registry.json"


def applied_path() -> Path:
    return runtime_dir() / "applied.json"


def load_registry() -> dict[str, Any]:
    target = registry_path()
    if not target.is_file():
        return {"adapters": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"adapters": {}}
    if not isinstance(data, dict):
        return {"adapters": {}}
    adapters = data.get("adapters") or {}
    if not isinstance(adapters, dict):
        adapters = {}
    return {"adapters": adapters}


def save_registry(data: dict[str, Any]) -> None:
    target = registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def register(
    adapter: Path,
    *,
    base: str,
    adapter_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if base not in ALLOWED_BASES:
        raise LoraError(f"unsupported base {base}; allowed: {sorted(ALLOWED_BASES)}")
    if not is_gguf(adapter):
        raise LoraError("adapter must be a GGUF file (magic GGUF)")
    dest_dir = runtime_dir() / "adapters"
    dest = dest_dir / f"{adapter_id}.gguf"
    record = {
        "id": adapter_id,
        "base": base,
        "source": str(adapter),
        "path": str(dest),
        "sha256": _sha256_file(adapter),
        "bytes": adapter.stat().st_size,
        "registered_at": _utc_now(),
    }
    if dry_run:
        record["dry_run"] = True
        return record
    dest_dir.mkdir(parents=True, exist_ok=True)
    if adapter.resolve() != dest.resolve():
        shutil.copy2(adapter, dest)
        record["sha256"] = _sha256_file(dest)
        record["bytes"] = dest.stat().st_size
    registry = load_registry()
    registry["adapters"][adapter_id] = record
    save_registry(registry)
    return record


def apply_adapter(adapter_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    registry = load_registry()
    record = registry.get("adapters", {}).get(adapter_id)
    if not isinstance(record, dict):
        raise LoraError(f"unknown adapter id: {adapter_id}")
    payload = {
        "id": adapter_id,
        "base": record.get("base"),
        "path": record.get("path"),
        "llama_cpp_args": ["--lora", f"/lora/{adapter_id}.gguf"],
        "pending_profile_restart": True,
        "applied_at": _utc_now(),
    }
    if dry_run:
        payload["dry_run"] = True
        return payload
    target = applied_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def disable(*, dry_run: bool = False) -> dict[str, Any]:
    target = applied_path()
    payload = {"disabled": True, "path": str(target)}
    if dry_run:
        payload["dry_run"] = True
        return payload
    if target.is_file():
        target.unlink()
    payload["removed"] = True
    return payload


def status() -> dict[str, Any]:
    applied = None
    target = applied_path()
    if target.is_file():
        try:
            loaded = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                applied = loaded
        except (OSError, ValueError):
            applied = None
    return {
        "classification": "optional_profile",
        "train_implemented": False,
        "example_dataset": str(example_dataset()),
        "runtime": str(runtime_dir()),
        "adapters": load_registry().get("adapters") or {},
        "applied": applied,
    }


def _print(data: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(json.dumps(data, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Optional LoRA dataset/plan/register/apply. No GPU trainer."
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    validate = sub.add_parser("validate")
    validate.add_argument("--dataset", default=str(example_dataset()))
    plan_cmd = sub.add_parser("plan")
    plan_cmd.add_argument("--dataset", default=str(example_dataset()))
    plan_cmd.add_argument("--base", default="qwen38-27b-q4")
    plan_cmd.add_argument("--id", default="station-ops")
    train = sub.add_parser("train")
    train.add_argument("--dataset", default=str(example_dataset()))
    train.add_argument("--base", default="qwen38-27b-q4")
    train.add_argument("--confirm", action="store_true")
    register_cmd = sub.add_parser("register")
    register_cmd.add_argument("--adapter", required=True)
    register_cmd.add_argument("--base", default="qwen38-27b-q4")
    register_cmd.add_argument("--id", required=True)
    register_cmd.add_argument("--dry-run", action="store_true")
    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("--id", required=True)
    apply_cmd.add_argument("--dry-run", action="store_true")
    disable_cmd = sub.add_parser("disable")
    disable_cmd.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    as_json = bool(args.json)
    try:
        if args.command == "status":
            _print(status(), as_json)
            return 0
        if args.command == "validate":
            _print(validate_dataset(Path(args.dataset)), as_json)
            return 0
        if args.command == "plan":
            _print(
                plan(Path(args.dataset), base=args.base, adapter_id=args.id),
                as_json,
            )
            return 0
        if args.command == "train":
            print(
                "ERROR: live LoRA training is not implemented on the station.",
                file=sys.stderr,
            )
            print(
                "Validate and plan with: ai lora plan --dataset PATH --base ID",
                file=sys.stderr,
            )
            print(
                "Convert a PEFT adapter to GGUF off-box, then ai lora register.",
                file=sys.stderr,
            )
            return 2
        if args.command == "register":
            _print(
                register(
                    Path(args.adapter),
                    base=args.base,
                    adapter_id=args.id,
                    dry_run=args.dry_run,
                ),
                as_json,
            )
            return 0
        if args.command == "apply":
            _print(apply_adapter(args.id, dry_run=args.dry_run), as_json)
            return 0
        if args.command == "disable":
            _print(disable(dry_run=args.dry_run), as_json)
            return 0
    except LoraError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        "Usage: ai lora status|validate|plan|train|register|apply|disable",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
