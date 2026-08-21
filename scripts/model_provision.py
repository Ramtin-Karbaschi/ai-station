#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import time
from typing import Any

def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(16 * 1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def load_manifest(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("schema_version") != 1:
        raise RuntimeError(
            "Unsupported model-manifest schema version."
        )

    return data


def selected_models(
    manifest: dict[str, Any],
    profile: str,
    model_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    if model_ids:
        by_id = {model["id"]: model for model in manifest.get("models", [])}
        unknown = sorted(set(model_ids) - set(by_id))
        if unknown:
            raise RuntimeError(f"Unknown model id(s): {', '.join(unknown)}")
        return [by_id[model_id] for model_id in model_ids]

    profiles = manifest.get("profiles", {})

    if profile not in profiles:
        raise RuntimeError(
            f"Unknown model profile: {profile}"
        )

    return [
        model
        for model in manifest.get("models", [])
        if profile in model.get("profiles", [])
    ]


def verify_model(
    model: dict[str, Any],
    data_root: pathlib.Path,
) -> bool:
    destination = data_root / model["destination"]

    if not destination.is_file():
        print(
            f"MISSING: {model['id']} -> {destination}"
        )
        return False

    size = destination.stat().st_size

    if size != model["size_bytes"]:
        print(
            f"INVALID SIZE: {model['id']} | "
            f"expected={model['size_bytes']} actual={size}"
        )
        return False

    digest = sha256_file(destination)

    if digest.lower() != model["sha256"].lower():
        print(
            f"INVALID SHA256: {model['id']} | "
            f"expected={model['sha256']} actual={digest}"
        )
        return False

    print(
        f"OK: {model['id']} | "
        f"{size} bytes | {digest}"
    )

    return True


def install_model(
    model: dict[str, Any],
    data_root: pathlib.Path,
    cache_dir: pathlib.Path,
    token: str | None,
) -> None:
    # Keep list/help/verify usable without the download-only dependency.
    from huggingface_hub import hf_hub_download

    destination = data_root / model["destination"]
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if verify_model(model, data_root):
        print(f"SKIP: {model['id']} already verified.")
        return

    if destination.exists():
        quarantine = destination.with_name(
            destination.name
            + ".invalid-"
            + time.strftime("%Y%m%d-%H%M%S")
        )

        destination.rename(quarantine)

        print(
            f"Moved invalid file to: {quarantine}"
        )

    print()
    print(f"Downloading: {model['id']}")
    print(f"Repository:  {model['repo_id']}")
    print(f"Revision:    {model['revision']}")
    print(f"Filename:    {model['filename']}")
    print(f"Destination: {destination}")

    downloaded = pathlib.Path(
        hf_hub_download(
            repo_id=model["repo_id"],
            filename=model["filename"],
            revision=model["revision"],
            cache_dir=str(cache_dir),
            token=token,
        )
    )

    downloaded_size = downloaded.stat().st_size

    if downloaded_size != model["size_bytes"]:
        raise RuntimeError(
            "Downloaded model size is invalid:\n"
            f"  Model: {model['id']}\n"
            f"  Expected: {model['size_bytes']}\n"
            f"  Actual:   {downloaded_size}"
        )

    downloaded_sha = sha256_file(downloaded)

    if downloaded_sha.lower() != model["sha256"].lower():
        raise RuntimeError(
            "Downloaded model checksum is invalid:\n"
            f"  Model: {model['id']}\n"
            f"  Expected: {model['sha256']}\n"
            f"  Actual:   {downloaded_sha}"
        )

    temporary = destination.with_name(
        destination.name + ".partial"
    )

    temporary.unlink(missing_ok=True)

    try:
        os.link(downloaded, temporary)
    except OSError:
        shutil.copyfile(downloaded, temporary)

    os.chmod(temporary, 0o644)
    os.replace(temporary, destination)

    if not verify_model(model, data_root):
        raise RuntimeError(
            f"Final verification failed: {model['id']}"
        )

    print(f"INSTALLED: {model['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Provision and verify AI Station models."
        )
    )

    parser.add_argument(
        "--manifest",
        required=True,
    )

    parser.add_argument(
        "--data-root",
        default="/srv/ai-station",
    )

    parser.add_argument(
        "--profile",
        default="core",
    )

    parser.add_argument(
        "--id",
        dest="model_ids",
        action="append",
        default=[],
        help="select one manifest model id (repeatable; overrides --profile)",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="list the selected manifest entries without downloading or hashing",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON with --list",
    )

    parser.add_argument(
        "--verify-only",
        action="store_true",
    )

    args = parser.parse_args()

    manifest_path = pathlib.Path(
        args.manifest
    ).resolve()

    data_root = pathlib.Path(
        args.data_root
    ).resolve()

    manifest = load_manifest(manifest_path)
    models = selected_models(
        manifest,
        args.profile,
        args.model_ids,
    )

    if not models:
        raise RuntimeError(
            "No models are defined for the selected profile."
        )

    if args.list:
        rows = [
            {
                "id": model["id"],
                "role": model["role"],
                "profiles": model["profiles"],
                "destination": model["destination"],
                "size_bytes": model["size_bytes"],
                "installed": (data_root / model["destination"]).is_file(),
            }
            for model in models
        ]
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True))
        else:
            for row in rows:
                marker = "installed" if row["installed"] else "missing"
                size_gib = row["size_bytes"] / (1024**3)
                print(
                    f"{row['id']:<42} {marker:<9} {size_gib:>6.2f} GiB  "
                    f"{row['role']}"
                )
        return 0

    token = os.getenv("HF_TOKEN") or None
    failures = 0

    if args.verify_only:
        for model in models:
            if not verify_model(
                model,
                data_root,
            ):
                failures += 1

        print()
        print(
            f"Model verification failures: {failures}"
        )

        return 1 if failures else 0

    cache_dir = data_root / "cache" / "huggingface"
    cache_dir.mkdir(parents=True, exist_ok=True)

    for model in models:
        install_model(
            model,
            data_root,
            cache_dir,
            token,
        )

    print()
    print(
        "MODELS INSTALLED: "
        + (", ".join(args.model_ids) if args.model_ids else f"profile={args.profile}")
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(
            "\nInterrupted by user.",
            file=sys.stderr,
        )
        raise SystemExit(130)
    except Exception as exc:
        print(
            f"\nERROR: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)
