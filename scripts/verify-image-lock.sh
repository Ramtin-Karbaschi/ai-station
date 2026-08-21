#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT/compose.images.lock.yaml"
MANIFEST_FILE="$ROOT/config/image-lock.json"
TEMP_DIR="$(mktemp -d)"
COMPOSE_JSON="$TEMP_DIR/locked-compose.json"
trap 'rm -rf -- "$TEMP_DIR"' EXIT

require_local="${AI_STATION_IMAGE_LOCK_REQUIRE_LOCAL:-0}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --require-local)
            require_local=1
            shift
            ;;
        -h|--help)
            cat <<'EOF'
Usage: ./scripts/verify-image-lock.sh [--require-local]

Confirms Compose resolves every registry service to the digest in
config/image-lock.json. --require-local (or
AI_STATION_IMAGE_LOCK_REQUIRE_LOCAL=1) also fails when those images are
not present on this Docker engine. CI and make check stay pin-only;
install/verify after pull use --require-local.
EOF
            exit 0
            ;;
        *)
            echo "ERROR: unknown image-lock argument: $1" >&2
            exit 2
            ;;
    esac
done
export AI_STATION_IMAGE_LOCK_REQUIRE_LOCAL="$require_local"

cd "$ROOT"

echo "============================================================"
echo " AI Station - Docker image lock verification"
echo "============================================================"

if [[ ! -f "$LOCK_FILE" ]]; then
    echo "FAIL: compose.images.lock.yaml is missing."
    exit 1
fi

if [[ ! -f "$MANIFEST_FILE" ]]; then
    echo "FAIL: config/image-lock.json is missing."
    exit 1
fi

if ! grep -Eq \
    '^COMPOSE_FILE=compose\.yml:compose\.models\.yml:compose\.hardening\.yaml:compose\.local-builds\.yaml:compose\.images\.lock\.yaml$' \
    .env; then
    echo "FAIL: .env does not activate the image lock."
    exit 1
fi

# Enable all profiles so profile-gated model services are also verified
# against the image lock.
docker compose --profile '*' config --quiet
docker compose --profile '*' config --no-path-resolution --format json > "$COMPOSE_JSON"

python3 - \
    "$ROOT" \
    "$COMPOSE_JSON" \
    "$MANIFEST_FILE" <<'PY'
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Any

root = pathlib.Path(sys.argv[1])
config = json.loads(
    pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
)
manifest = json.loads(
    pathlib.Path(sys.argv[3]).read_text(encoding="utf-8")
)

services: dict[str, dict[str, Any]] = config.get("services", {})
errors: list[str] = []


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )


def image_exists(reference: str) -> bool:
    return run(
        ["docker", "image", "inspect", reference]
    ).returncode == 0


def active_container(service: str) -> str | None:
    result = run(
        ["docker", "compose", "ps", "-q", service]
    )

    values = result.stdout.strip().splitlines()

    return values[0] if values else None


def container_image_id(container_id: str) -> str | None:
    result = run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.Image}}",
            container_id,
        ]
    )

    if result.returncode != 0:
        return None

    return result.stdout.strip() or None


def repo_digests(image_id: str) -> list[str]:
    result = run(
        [
            "docker",
            "image",
            "inspect",
            "--format",
            "{{json .RepoDigests}}",
            image_id,
        ]
    )

    if result.returncode != 0:
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return []


for service_name, lock_data in manifest["services"].items():
    resolved = services.get(service_name)

    if resolved is None:
        errors.append(
            f"{service_name}: missing from Compose configuration"
        )
        continue

    source_type = lock_data["source_type"]

    if source_type == "registry":
        expected = lock_data["locked_image"]
        resolved_image = resolved.get("image", "")

        if resolved_image != expected:
            errors.append(
                f"{service_name}: resolved image differs from lock"
            )
            continue

        if "@sha256:" not in resolved_image:
            errors.append(
                f"{service_name}: image is not digest-pinned"
            )
            continue

        require_local = os.environ.get(
            "AI_STATION_IMAGE_LOCK_REQUIRE_LOCAL", ""
        ).strip() in {"1", "true", "yes"}

        if require_local and not image_exists(resolved_image):
            configured = lock_data.get("configured_image")

            if configured and not image_exists(configured):
                errors.append(
                    f"{service_name}: locked image is unavailable locally"
                )

        container_id = active_container(service_name)

        if container_id:
            image_id = container_image_id(container_id)

            if image_id:
                expected_digest = expected.split("@", 1)[1]
                current_digests = {
                    item.split("@", 1)[1]
                    for item in repo_digests(image_id)
                    if "@sha256:" in item
                }

                if (
                    current_digests
                    and expected_digest not in current_digests
                ):
                    errors.append(
                        f"{service_name}: running container does not "
                        "match locked digest"
                    )

    elif source_type == "local-build":
        if resolved.get("pull_policy") != "build":
            errors.append(
                f"{service_name}: expected pull_policy=build"
            )

    elif source_type == "local-artifact":
        if resolved.get("pull_policy") != "never":
            errors.append(
                f"{service_name}: expected pull_policy=never"
            )

        image = lock_data.get("required_local_image")

        if not image or not image_exists(image):
            errors.append(
                f"{service_name}: required local image is missing"
            )

    else:
        errors.append(
            f"{service_name}: unknown source type {source_type}"
        )

if errors:
    for error in errors:
        print(f"FAIL: {error}")

    print()
    print(f"Image lock errors: {len(errors)}")
    raise SystemExit(1)

summary = manifest["summary"]

print(
    "OK: Registry digest services: "
    f"{summary['registry_digest_services']}"
)
print(
    "OK: Repository build services: "
    f"{summary['local_build_services']}"
)
print(
    "OK: Local artifact services: "
    f"{summary['local_artifact_services']}"
)
print("OK: Docker image lock is valid.")
PY

echo
echo "IMAGE LOCK VERIFICATION PASSED"
