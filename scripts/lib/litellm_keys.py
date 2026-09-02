#!/usr/bin/env python3
"""LiteLLM virtual-key helpers. Never print API secrets."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterator

DEFAULT_BASE = "http://127.0.0.1:4000"
ENV_PATH = Path("/opt/ai-station/.env")


def load_env_value(key: str, path: Path = ENV_PATH) -> str:
    if not path.is_file():
        return ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return ""


def generate_payload(
    alias: str,
    models: list[str],
    *,
    rpm: int | None = None,
    tpm: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key_alias": alias,
        "models": models,
        "metadata": {"project": alias, "platform": "ai-station"},
    }
    if rpm is not None:
        payload["rpm_limit"] = rpm
    if tpm is not None:
        payload["tpm_limit"] = tpm
    return payload


def _request(
    method: str,
    path: str,
    *,
    master: str,
    base: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {master}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        exc.read()
        raise SystemExit(f"ERROR: LiteLLM {method} {path} HTTP {exc.code}") from None
    if not body:
        return {}
    return json.loads(body)


def iter_keys(master: str, base: str = DEFAULT_BASE) -> Iterator[dict[str, Any]]:
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "return_full_object": "true",
                "page": page,
                "size": 100,
            }
        )
        body = _request("GET", f"/key/list?{query}", master=master, base=base)
        keys = body.get("keys") if isinstance(body, dict) else None
        if not isinstance(keys, list):
            return
        for item in keys:
            if isinstance(item, dict):
                yield item
        total_pages = int(body.get("total_pages") or 1)
        if page >= total_pages:
            return
        page += 1


def clear_rate_limits(
    master: str,
    *,
    alias: str | None = None,
    base: str = DEFAULT_BASE,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    found = False
    for item in iter_keys(master, base):
        key_alias = str(item.get("key_alias") or "")
        token = str(item.get("token") or "")
        if not token:
            continue
        if alias is not None and key_alias != alias:
            continue
        found = True
        tpm = item.get("tpm_limit")
        rpm = item.get("rpm_limit")
        if tpm is None and rpm is None:
            results.append(
                {
                    "alias": key_alias or "(unnamed)",
                    "tpm_limit": None,
                    "rpm_limit": None,
                    "changed": False,
                }
            )
            continue
        updated = _request(
            "POST",
            "/key/update",
            master=master,
            base=base,
            payload={"key": token, "tpm_limit": None, "rpm_limit": None},
        )
        info = updated if isinstance(updated, dict) else {}
        results.append(
            {
                "alias": str(info.get("key_alias") or key_alias or "(unnamed)"),
                "tpm_limit": info.get("tpm_limit"),
                "rpm_limit": info.get("rpm_limit"),
                "changed": True,
            }
        )
    if alias is not None and not found:
        raise SystemExit(f"ERROR: LiteLLM key alias not found: {alias}")
    return results


def _parse_optional_int(raw: str | None, flag: str) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {flag} must be a positive integer") from exc
    if value <= 0:
        raise SystemExit(f"ERROR: {flag} must be a positive integer")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LiteLLM virtual-key helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate-payload", help="Print /key/generate JSON")
    gen.add_argument("--alias", required=True)
    gen.add_argument("--models", required=True)
    gen.add_argument("--rpm", default="")
    gen.add_argument("--tpm", default="")

    unlimit = sub.add_parser("unlimit", help="Clear TPM/RPM on virtual keys")
    unlimit.add_argument("--alias", default="")
    unlimit.add_argument("--base", default=DEFAULT_BASE)

    args = parser.parse_args(argv)
    if args.command == "generate-payload":
        models = [item.strip() for item in args.models.split(",") if item.strip()]
        payload = generate_payload(
            args.alias,
            models,
            rpm=_parse_optional_int(args.rpm, "--rpm"),
            tpm=_parse_optional_int(args.tpm, "--tpm"),
        )
        json.dump(payload, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0

    master = load_env_value("LITELLM_MASTER_KEY")
    if not master:
        print("ERROR: LITELLM_MASTER_KEY is not set in .env", file=sys.stderr)
        return 1
    alias = args.alias.strip() or None
    rows = clear_rate_limits(master, alias=alias, base=args.base)
    changed = 0
    for row in rows:
        if row["changed"]:
            changed += 1
        print(
            "OK: LiteLLM key "
            f"{row['alias']} tpm={row['tpm_limit'] if row['tpm_limit'] is not None else 'none'} "
            f"rpm={row['rpm_limit'] if row['rpm_limit'] is not None else 'none'}"
            + (" (cleared)" if row["changed"] else " (already unlimited)")
        )
    print(f"OK: {changed} key(s) cleared, {len(rows) - changed} already unlimited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
