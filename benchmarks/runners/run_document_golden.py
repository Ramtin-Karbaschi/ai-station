#!/usr/bin/env python3
"""Tika baseline runner for the document golden set (Phase 5)."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
DIGIT_RUN_RE = re.compile(r"\d+")


def extract_tika(endpoint: str, path: Path, timeout: float) -> tuple[str, float]:
    data = path.read_bytes()
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/tika",
        data=data,
        headers={
            "Accept": "text/plain",
            "Content-Type": "application/octet-stream",
        },
        method="PUT",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8", errors="replace")
    latency_ms = (time.perf_counter() - started) * 1000
    return text, latency_ms


def score_fixture(fixture: dict[str, Any], text: str, latency_ms: float) -> dict[str, Any]:
    missing = [
        needle
        for needle in fixture.get("required_substrings") or []
        if needle not in text
    ]
    persian_ok = True
    if fixture.get("require_persian"):
        persian_ok = bool(PERSIAN_RE.search(text))
    digit_runs = DIGIT_RUN_RE.findall(text)
    min_digits = int(fixture.get("min_digit_runs") or 0)
    digits_ok = len(digit_runs) >= min_digits
    max_latency = fixture.get("max_latency_ms")
    latency_ok = True if max_latency is None else latency_ms <= float(max_latency)
    ok = not missing and persian_ok and digits_ok and latency_ok
    return {
        "id": fixture["id"],
        "class": fixture["class"],
        "ok": ok,
        "latency_ms": latency_ms,
        "missing_substrings": missing,
        "persian_ok": persian_ok,
        "digit_runs": len(digit_runs),
        "digits_ok": digits_ok,
        "latency_ok": latency_ok,
        "excerpt": text[:240].replace("\n", " "),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="benchmarks/datasets/documents/golden_manifest.json",
    )
    parser.add_argument("--tika", default="http://127.0.0.1:9998")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    manifest_path = (root / args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    results: list[dict[str, Any]] = []
    failures = 0
    for fixture in manifest["fixtures"]:
        path = root / fixture["path"]
        try:
            text, latency_ms = extract_tika(args.tika, path, args.timeout)
            scored = score_fixture(fixture, text, latency_ms)
        except Exception as exc:  # noqa: BLE001 - record fixture failure
            scored = {
                "id": fixture["id"],
                "class": fixture["class"],
                "ok": False,
                "error": str(exc),
            }
        if not scored.get("ok"):
            failures += 1
        results.append(scored)

    payload = {
        "engine": "tika",
        "suite_id": manifest.get("suite_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.tika,
        "fixture_count": len(results),
        "pass_count": sum(1 for item in results if item.get("ok")),
        "fail_count": failures,
        "fixtures": results,
        "decision_note": (
            "Tika baseline only. Docling remains uninstalled until classes "
            "with measured wins are identified (ADR-006)."
        ),
    }
    text = json.dumps(payload, indent=2) + "\n"
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    print(text)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
