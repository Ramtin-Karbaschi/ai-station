#!/usr/bin/env python3
"""Logical tenant registry (ADR-036). Isolation is LiteLLM projects, not a second DB."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TENANT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
DEFAULT_MODELS = ("Qwen3.8-27B-UD-Q4_K_M",)


class TenantError(RuntimeError):
    """Tenant registry failed."""


def data_root() -> Path:
    return Path(os.environ.get("AI_STATION_DATA", "/srv/ai-station")).resolve()


def registry_path() -> Path:
    override = os.environ.get("AI_STATION_TENANT_REGISTRY")
    if override:
        return Path(override)
    return data_root() / "runtime" / "tenants" / "registry.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry(path: Path | None = None) -> dict[str, Any]:
    target = path or registry_path()
    if not target.is_file():
        return {"version": 1, "tenants": {}}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TenantError(f"cannot read {target}") from exc
    if not isinstance(data, dict):
        return {"version": 1, "tenants": {}}
    tenants = data.get("tenants") or {}
    if not isinstance(tenants, dict):
        tenants = {}
    return {"version": int(data.get("version") or 1), "tenants": tenants}


def save_registry(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or registry_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def key_alias_for(tenant_id: str) -> str:
    return f"tenant-{tenant_id}"


def validate_tenant_id(tenant_id: str) -> str:
    text = tenant_id.strip()
    if not TENANT_ID_RE.match(text):
        raise TenantError(
            "tenant id must be lowercase start-letter then [a-z0-9-] (2-32 chars)"
        )
    return text


def isolation_errors(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    aliases: dict[str, str] = {}
    tenants = registry.get("tenants") or {}
    for tenant_id, row in tenants.items():
        if not isinstance(row, dict):
            errors.append(f"{tenant_id}: invalid row")
            continue
        alias = str(row.get("key_alias") or "")
        if not alias:
            errors.append(f"{tenant_id}: missing key_alias")
            continue
        owner = aliases.get(alias)
        if owner and owner != tenant_id:
            errors.append(f"key alias {alias} shared by {owner} and {tenant_id}")
        aliases[alias] = str(tenant_id)
    return errors


def doctor(registry: dict[str, Any] | None = None) -> dict[str, Any]:
    data = registry if registry is not None else load_registry()
    errors = isolation_errors(data)
    return {
        "ok": not errors,
        "tenant_count": len(data.get("tenants") or {}),
        "errors": errors,
        "open_webui_partitioned": False,
        "isolation": "litellm_project_keys",
    }


def create(
    tenant_id: str,
    *,
    models: list[str] | None = None,
    dry_run: bool = False,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tid = validate_tenant_id(tenant_id)
    data = registry if registry is not None else load_registry()
    tenants = data.setdefault("tenants", {})
    if tid in tenants:
        raise TenantError(f"tenant already exists: {tid}")
    alias = key_alias_for(tid)
    for other_id, row in tenants.items():
        if isinstance(row, dict) and row.get("key_alias") == alias:
            raise TenantError(f"key alias {alias} already used by {other_id}")
    allow = list(models) if models else list(DEFAULT_MODELS)
    row = {
        "id": tid,
        "key_alias": alias,
        "models": allow,
        "created_at": _utc_now(),
        "provision_command": (
            f"ai projects create {alias} --models " + ",".join(allow)
        ),
    }
    if dry_run:
        preview = dict(data)
        preview_tenants = dict(tenants)
        preview_tenants[tid] = row
        preview["tenants"] = preview_tenants
        check = doctor(preview)
        if not check["ok"]:
            raise TenantError("; ".join(check["errors"]))
        return {"dry_run": True, "tenant": row, "doctor": check}
    tenants[tid] = row
    check = doctor(data)
    if not check["ok"]:
        raise TenantError("; ".join(check["errors"]))
    save_registry(data)
    return {"tenant": row, "doctor": check}


def disable(tenant_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    tid = validate_tenant_id(tenant_id)
    data = load_registry()
    tenants = data.get("tenants") or {}
    if tid not in tenants:
        raise TenantError(f"unknown tenant: {tid}")
    row = tenants[tid]
    if dry_run:
        return {"dry_run": True, "would_remove": tid, "revoke_hint": f"ai projects revoke {row.get('key_alias')}"}
    tenants.pop(tid)
    data["tenants"] = tenants
    save_registry(data)
    return {
        "removed": tid,
        "revoke_hint": f"ai projects revoke {row.get('key_alias')}",
    }


def show(tenant_id: str) -> dict[str, Any]:
    tid = validate_tenant_id(tenant_id)
    row = (load_registry().get("tenants") or {}).get(tid)
    if not isinstance(row, dict):
        raise TenantError(f"unknown tenant: {tid}")
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Logical tenants: one LiteLLM project key per tenant."
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    sub.add_parser("list")
    sub.add_parser("doctor")
    create_cmd = sub.add_parser("create")
    create_cmd.add_argument("tenant_id")
    create_cmd.add_argument("--models", default="")
    create_cmd.add_argument("--dry-run", action="store_true")
    show_cmd = sub.add_parser("show")
    show_cmd.add_argument("tenant_id")
    disable_cmd = sub.add_parser("disable")
    disable_cmd.add_argument("tenant_id")
    disable_cmd.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            data = load_registry()
            report = doctor(data)
            report["tenants"] = sorted((data.get("tenants") or {}).keys())
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 2
        if args.command == "list":
            print(json.dumps(load_registry(), indent=2))
            return 0
        if args.command == "doctor":
            report = doctor()
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 2
        if args.command == "create":
            models = [item.strip() for item in args.models.split(",") if item.strip()] or None
            print(
                json.dumps(
                    create(args.tenant_id, models=models, dry_run=args.dry_run),
                    indent=2,
                )
            )
            return 0
        if args.command == "show":
            print(json.dumps(show(args.tenant_id), indent=2))
            return 0
        if args.command == "disable":
            print(json.dumps(disable(args.tenant_id, dry_run=args.dry_run), indent=2))
            return 0
    except TenantError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print("Usage: ai tenants status|list|create|show|disable|doctor", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
