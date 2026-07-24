#!/usr/bin/env python3
"""Provision an experimental Hugging Face snapshot under /srv/ai-station/models."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from typing import Any

from huggingface_hub import snapshot_download


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(16 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument(
        "--destination",
        required=True,
        help="Relative to data-root/models",
    )
    parser.add_argument("--data-root", default="/srv/ai-station")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--expected-manifest", default="")
    args = parser.parse_args()

    data_root = pathlib.Path(args.data_root)
    dest = data_root / "models" / args.destination
    cache_dir = data_root / "cache" / "huggingface"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)

    expected: list[dict[str, Any]] = []
    if args.expected_manifest:
        expected = json.loads(
            pathlib.Path(args.expected_manifest).read_text(encoding="utf-8")
        )

    if not args.verify_only:
        print(f"Downloading snapshot {args.repo_id}@{args.revision} -> {dest}")
        snapshot_download(
            repo_id=args.repo_id,
            revision=args.revision,
            local_dir=str(dest),
            cache_dir=str(cache_dir),
            token=os.getenv("HF_TOKEN") or None,
        )

    failures = 0
    records = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"SHA256SUMS.json", "AI_STATION_SNAPSHOT.json"}:
            continue
        rel = str(path.relative_to(dest)).replace("\\", "/")
        size = path.stat().st_size
        digest = sha256_file(path)
        records.append({"filename": rel, "sha256": digest, "size_bytes": size})
        print(f"OK: {rel} {size} {digest}")

    (dest / "SHA256SUMS.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )

    if expected:
        by_name = {item["filename"]: item for item in records}
        for item in expected:
            name = item["filename"]
            got = by_name.get(name)
            if got is None:
                print(f"MISSING: {name}")
                failures += 1
                continue
            if got["sha256"].lower() != item["sha256"].lower():
                print(f"SHA mismatch: {name}")
                failures += 1
            if got["size_bytes"] != int(item["size_bytes"]):
                print(f"SIZE mismatch: {name}")
                failures += 1

    meta = {
        "repo_id": args.repo_id,
        "revision": args.revision,
        "destination": args.destination,
        "file_count": len(records),
    }
    (dest / "AI_STATION_SNAPSHOT.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Snapshot files: {len(records)}; failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
