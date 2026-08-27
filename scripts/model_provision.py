#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

HUB_DOWNLOAD_TIMEOUT_SECONDS = 600
HUB_ETAG_TIMEOUT_SECONDS = 120
HUB_DOWNLOAD_ATTEMPTS = 5
HTTP_USER_AGENT = "ai-station-provisioner"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(16 * 1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def configure_hub_client() -> None:
    # huggingface_hub reads these at import time (default download timeout is 10s).
    os.environ.setdefault(
        "HF_HUB_DOWNLOAD_TIMEOUT",
        str(HUB_DOWNLOAD_TIMEOUT_SECONDS),
    )
    os.environ.setdefault(
        "HF_HUB_ETAG_TIMEOUT",
        str(HUB_ETAG_TIMEOUT_SECONDS),
    )
    os.environ.setdefault("HF_XET_HIGH_PERFORMANCE", "1")
    # Xet on this workstation stalls near completion with no byte progress.
    # Prefer classic HTTPS / hf_transfer unless the caller opts back into Xet.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "1")


def hub_lock_dir(cache_dir: pathlib.Path, repo_id: str) -> pathlib.Path:
    return cache_dir / ".locks" / ("models--" + repo_id.replace("/", "--"))


def clear_stale_hub_locks(cache_dir: pathlib.Path, repo_id: str) -> int:
    lock_dir = hub_lock_dir(cache_dir, repo_id)
    if not lock_dir.is_dir():
        return 0

    removed = 0
    for lock in lock_dir.glob("*.lock"):
        try:
            lock.unlink()
        except OSError:
            continue
        removed += 1
    return removed


def huggingface_resolve_url(repo_id: str, revision: str, filename: str) -> str:
    return (
        f"https://huggingface.co/{repo_id}/resolve/{revision}/{filename}"
    )


def is_incomplete_destination(path: pathlib.Path, size_bytes: int) -> bool:
    return path.is_file() and 0 < path.stat().st_size < size_bytes


def is_retryable_download_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    needles = (
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection",
        "reset by peer",
        "lock",
        "429",
        "503",
        "ssl",
        "incomplete",
        "temporary failure",
    )
    return any(needle in text for needle in needles)


def _write_http_auth_conf(token: str, *, kind: str) -> pathlib.Path:
    prefix = "ai-station-aria2-" if kind == "aria2" else "ai-station-curl-"
    suffix = ".conf" if kind == "aria2" else ".cfg"
    handle, name = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    path = pathlib.Path(name)
    if kind == "aria2":
        body = f"header=Authorization: Bearer {token}\n"
    else:
        body = f'header = "Authorization: Bearer {token}"\n'
    os.write(handle, body.encode("utf-8"))
    os.close(handle)
    os.chmod(path, 0o600)
    return path


def resolve_download_url(
    url: str,
    *,
    token: str | None = None,
    user_agent: str = HTTP_USER_AGENT,
) -> str:
    command = [
        "curl",
        "-fsSL",
        "-A",
        user_agent,
        "-o",
        os.devnull,
        "-w",
        "%{url_effective}",
        "--max-redirs",
        "8",
        "--connect-timeout",
        "30",
        "--max-time",
        "12",
        url,
    ]
    auth_conf: pathlib.Path | None = None
    if token:
        auth_conf = _write_http_auth_conf(token, kind="curl")
        command[1:1] = ["-K", str(auth_conf)]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return url
    finally:
        if auth_conf is not None:
            auth_conf.unlink(missing_ok=True)

    resolved = completed.stdout.strip()
    return resolved or url


def http_resume_download(
    url: str,
    dest: pathlib.Path,
    *,
    token: str | None = None,
    user_agent: str = HTTP_USER_AGENT,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    source = resolve_download_url(
        url,
        token=token,
        user_agent=user_agent,
    )
    auth_conf: pathlib.Path | None = None
    try:
        if shutil.which("aria2c"):
            command = [
                "aria2c",
                "--continue=true",
                "--max-connection-per-server=16",
                "--split=16",
                "--min-split-size=1M",
                "--file-allocation=none",
                "--max-tries=40",
                "--retry-wait=5",
                "--timeout=120",
                "--connect-timeout=30",
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
                f"--user-agent={user_agent}",
                "--console-log-level=notice",
                "--summary-interval=30",
                "-d",
                str(dest.parent),
                "-o",
                dest.name,
            ]
            if token:
                auth_conf = _write_http_auth_conf(token, kind="aria2")
                command.insert(1, f"--conf-path={auth_conf}")
            command.append(source)
        else:
            command = [
                "curl",
                "-fL",
                "--retry",
                "40",
                "--retry-delay",
                "4",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "--speed-limit",
                "8192",
                "--speed-time",
                "60",
                "-C",
                "-",
                "-A",
                user_agent,
            ]
            if token:
                auth_conf = _write_http_auth_conf(token, kind="curl")
                command.extend(["-K", str(auth_conf)])
            command.extend(["-o", str(dest), source])

        completed = subprocess.run(command, check=False)
    finally:
        if auth_conf is not None:
            auth_conf.unlink(missing_ok=True)

    if completed.returncode != 0:
        raise RuntimeError(
            f"HTTP resume download failed (exit {completed.returncode}): {dest}"
        )


def load_hf_token() -> str | None:
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        value = os.getenv(key)
        if value:
            return value
    token_path = pathlib.Path.home() / ".cache" / "huggingface" / "token"
    if token_path.is_file():
        text = token_path.read_text(encoding="utf-8").strip()
        return text or None
    return None


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


def _place_verified_download(
    model: dict[str, Any],
    downloaded: pathlib.Path,
    destination: pathlib.Path,
) -> None:
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


def install_model(
    model: dict[str, Any],
    data_root: pathlib.Path,
    cache_dir: pathlib.Path,
    token: str | None,
) -> None:
    configure_hub_client()

    destination = data_root / model["destination"]
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if model.get("conversion") and not destination.is_file():
        raise RuntimeError(
            f"{model['id']} is a converted artifact; run "
            f"{model['conversion'].get('script', 'the recorded convert script')} "
            "instead of downloading a community GGUF."
        )

    if verify_model(model, data_root):
        print(f"SKIP: {model['id']} already verified.")
        return

    if destination.exists() and not is_incomplete_destination(
        destination,
        model["size_bytes"],
    ):
        if destination.stat().st_size == 0:
            destination.unlink()
        else:
            quarantine = destination.with_name(
                destination.name
                + ".invalid-"
                + time.strftime("%Y%m%d-%H%M%S")
            )
            destination.rename(quarantine)
            print(f"Moved invalid file to: {quarantine}")

    print()
    print(f"Downloading: {model['id']}")
    print(f"Repository:  {model['repo_id']}")
    print(f"Revision:    {model['revision']}")
    print(f"Filename:    {model['filename']}")
    print(f"Destination: {destination}")

    resolve_url = huggingface_resolve_url(
        model["repo_id"],
        model["revision"],
        model["filename"],
    )

    if model.get("conversion"):
        raise RuntimeError(
            f"{model['id']} failed checksum after conversion; re-run "
            f"{model['conversion'].get('script', 'the recorded convert script')}."
        )

    print("Downloading over HTTPS with aria2c/curl (Xet/hub last).")
    if destination.is_file():
        print(
            f"Resume from {destination.stat().st_size} of "
            f"{model['size_bytes']} bytes."
        )
    try:
        http_resume_download(
            resolve_url,
            destination,
            token=token,
        )
    except Exception as exc:
        print(f"HTTP download failed: {exc}")
    else:
        if verify_model(model, data_root):
            print(f"INSTALLED: {model['id']}")
            return

    # Keep list/help/verify usable without the download-only dependency.
    from huggingface_hub import hf_hub_download

    last_error: Exception | None = None
    downloaded: pathlib.Path | None = None

    for attempt in range(1, HUB_DOWNLOAD_ATTEMPTS + 1):
        removed = clear_stale_hub_locks(cache_dir, model["repo_id"])
        if removed:
            print(
                f"Cleared {removed} stale Hugging Face lock file(s)."
            )

        try:
            downloaded = pathlib.Path(
                hf_hub_download(
                    repo_id=model["repo_id"],
                    filename=model["filename"],
                    revision=model["revision"],
                    cache_dir=str(cache_dir),
                    token=token,
                    etag_timeout=int(
                        os.environ.get(
                            "HF_HUB_ETAG_TIMEOUT",
                            str(HUB_ETAG_TIMEOUT_SECONDS),
                        )
                    ),
                )
            )
            break
        except Exception as exc:
            last_error = exc
            print(
                f"Hub download attempt {attempt}/{HUB_DOWNLOAD_ATTEMPTS} "
                f"failed: {exc}"
            )
            if (
                not is_retryable_download_error(exc)
                or attempt == HUB_DOWNLOAD_ATTEMPTS
            ):
                break
            time.sleep(min(30, 4 * attempt))

    if downloaded is not None:
        _place_verified_download(model, downloaded, destination)
        if not verify_model(model, data_root):
            raise RuntimeError(
                f"Final verification failed: {model['id']}"
            )
        print(f"INSTALLED: {model['id']}")
        return

    print("Falling back to HTTP Range download of the destination file.")
    http_resume_download(
        resolve_url,
        destination,
        token=token,
    )
    if verify_model(model, data_root):
        print(f"INSTALLED: {model['id']}")
        return

    if last_error is not None:
        raise last_error
    raise RuntimeError(
        f"Download failed after hub retries and HTTP fallback: {model['id']}"
    )


def install_models(
    models: list[dict[str, Any]],
    data_root: pathlib.Path,
    cache_dir: pathlib.Path,
    token: str | None,
) -> list[str]:
    """Install each model. A gated or failed id does not abort the queue."""
    failures: list[str] = []
    for model in models:
        try:
            install_model(model, data_root, cache_dir, token)
        except Exception as exc:
            print(f"ERROR: {model['id']}: {exc}", file=sys.stderr)
            failures.append(str(model["id"]))
    return failures


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

    token = load_hf_token()
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

    failures_list = install_models(models, data_root, cache_dir, token)
    failures = len(failures_list)

    print()
    if failures_list:
        print("MODELS FAILED: " + ", ".join(failures_list))
    print(
        "MODELS INSTALLED: "
        + (", ".join(args.model_ids) if args.model_ids else f"profile={args.profile}")
    )

    return 1 if failures else 0


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
