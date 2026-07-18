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

from huggingface_hub import hf_hub_download


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
) -> list[dict[str, Any]]:
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
        choices=["core", "all"],
        default="core",
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

    cache_dir = (
        data_root
        / "cache"
        / "huggingface"
    )

    cache_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest = load_manifest(manifest_path)
    models = selected_models(
        manifest,
        args.profile,
    )

    if not models:
        raise RuntimeError(
            "No models are defined for the selected profile."
        )

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

    for model in models:
        install_model(
            model,
            data_root,
            cache_dir,
            token,
        )

    print()
    print(
        f"MODEL PROFILE INSTALLED: {args.profile}"
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
