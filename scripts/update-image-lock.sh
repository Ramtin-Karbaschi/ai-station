#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_COMPOSE="compose.yml:compose.hardening.yaml:compose.local-builds.yaml"
LOCK_FILE="compose.images.lock.yaml"
MANIFEST_FILE="config/image-lock.json"
SUMMARY_FILE="config/image-lock-summary.txt"
VERIFY_SCRIPT="scripts/verify-image-lock.sh"
DOC_FILE="docs/IMAGE_LOCK.md"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/srv/ai-station/backups/image-lock-${STAMP}"
TEMP_DIR="$(mktemp -d)"

echo "============================================================"
echo " AI Station - Immutable Docker image lock"
echo "============================================================"

cd "$ROOT"

for COMMAND in docker python3 git; do
    if ! command -v "$COMMAND" >/dev/null 2>&1; then
        echo "ERROR: Required command is missing: $COMMAND"
        exit 1
    fi
done

if ! docker compose version >/dev/null 2>&1; then
    echo "ERROR: Docker Compose v2 is unavailable."
    exit 1
fi

if [[ ! -f compose.yml || ! -f compose.hardening.yaml ]]; then
    echo "ERROR: Base Compose files are missing."
    exit 1
fi

mkdir -p "$BACKUP_DIR" config scripts docs
chmod 0700 "$BACKUP_DIR"

declare -a MANAGED_FILES=(
    ".env"
    ".env.example"
    "$LOCK_FILE"
    "$MANIFEST_FILE"
    "$SUMMARY_FILE"
    "$VERIFY_SCRIPT"
    "$DOC_FILE"
    "scripts/release-audit.sh"
)

declare -A FILE_EXISTED=()

for FILE in "${MANAGED_FILES[@]}"; do
    if [[ -e "$ROOT/$FILE" ]]; then
        FILE_EXISTED["$FILE"]=1
        mkdir -p "$BACKUP_DIR/$(dirname "$FILE")"
        cp -a "$ROOT/$FILE" "$BACKUP_DIR/$FILE"
    else
        FILE_EXISTED["$FILE"]=0
    fi
done

rollback() {
    EXIT_CODE=$?

    trap - ERR
    set +e

    echo
    echo "ERROR: Image-lock process failed."
    echo "Rolling back changed files..."

    for FILE in "${MANAGED_FILES[@]}"; do
        if [[ "${FILE_EXISTED[$FILE]}" == "1" ]]; then
            mkdir -p "$ROOT/$(dirname "$FILE")"
            cp -a "$BACKUP_DIR/$FILE" "$ROOT/$FILE"
        else
            rm -f "$ROOT/$FILE"
        fi
    done

    rm -rf "$TEMP_DIR"

    echo "Rollback completed."
    echo "Backup retained at:"
    echo "  $BACKUP_DIR"

    exit "$EXIT_CODE"
}

trap rollback ERR

PROJECT="$(
    docker inspect ai-station-open-webui-1 \
        --format '{{ index .Config.Labels "com.docker.compose.project" }}' \
        2>/dev/null || true
)"

if [[ -z "$PROJECT" ]]; then
    PROJECT="ai-station"
fi

echo
echo "Project:"
echo "  $PROJECT"

echo
echo "Base Compose files:"
echo "  $BASE_COMPOSE"

echo
echo "Rendering current Compose model..."

COMPOSE_FILE="$BASE_COMPOSE" \
    docker compose -p "$PROJECT" config --no-path-resolution --format json \
    > "$TEMP_DIR/compose-base.json"

COMPOSE_FILE="$BASE_COMPOSE" \
    docker compose -p "$PROJECT" config --quiet

echo "OK: Base Compose model is valid."

echo
echo "Resolving exact images from running containers and local image store..."

python3 - \
    "$ROOT" \
    "$PROJECT" \
    "$BASE_COMPOSE" \
    "$TEMP_DIR/compose-base.json" \
    "$TEMP_DIR/$LOCK_FILE" \
    "$TEMP_DIR/image-lock.json" \
    "$TEMP_DIR/image-lock-summary.txt" <<'PY'
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any

root = pathlib.Path(sys.argv[1])
project = sys.argv[2]
base_compose = sys.argv[3]
config_path = pathlib.Path(sys.argv[4])
lock_path = pathlib.Path(sys.argv[5])
manifest_path = pathlib.Path(sys.argv[6])
summary_path = pathlib.Path(sys.argv[7])

config = json.loads(config_path.read_text(encoding="utf-8"))
services: dict[str, dict[str, Any]] = config.get("services", {})

if not services:
    raise SystemExit("ERROR: No Compose services were detected.")


def run(
    args: list[str],
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()

    if env:
        merged_env.update(env)

    return subprocess.run(
        args,
        cwd=root,
        env=merged_env,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def compose(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        ["docker", "compose", "-p", project, *args],
        check=check,
        env={"COMPOSE_FILE": base_compose},
    )


def inspect_image(reference: str) -> dict[str, Any] | None:
    result = run(
        ["docker", "image", "inspect", reference],
        check=False,
    )

    if result.returncode != 0:
        return None

    data = json.loads(result.stdout)

    if not data:
        return None

    return data[0]


def inspect_container(container_id: str) -> dict[str, Any] | None:
    result = run(
        ["docker", "inspect", container_id],
        check=False,
    )

    if result.returncode != 0:
        return None

    data = json.loads(result.stdout)

    if not data:
        return None

    return data[0]


def image_repository(reference: str) -> str:
    reference = reference.split("@", 1)[0]

    final_part = reference.rsplit("/", 1)[-1]

    if ":" in final_part:
        reference = reference.rsplit(":", 1)[0]

    if "/" not in reference:
        return f"docker.io/library/{reference}"

    first = reference.split("/", 1)[0]

    if "." not in first and ":" not in first and first != "localhost":
        return f"docker.io/{reference}"

    return reference


def choose_repo_digest(
    configured_image: str,
    repo_digests: list[str],
) -> str | None:
    if not repo_digests:
        return None

    expected = image_repository(configured_image)

    for repo_digest in repo_digests:
        repository = repo_digest.split("@", 1)[0]

        if image_repository(repository) == expected:
            return repo_digest

    expected_tail = expected.removeprefix("docker.io/")

    for repo_digest in repo_digests:
        repository = repo_digest.split("@", 1)[0]
        normalized = image_repository(repository)
        normalized_tail = normalized.removeprefix("docker.io/")

        if normalized_tail == expected_tail:
            return repo_digest

    return repo_digests[0]


def get_container_id(service_name: str) -> str | None:
    result = compose(
        ["ps", "-q", service_name],
        check=False,
    )

    if result.returncode != 0:
        return None

    value = result.stdout.strip().splitlines()

    return value[0] if value else None


def pull_image(reference: str) -> bool:
    print(f"INFO: Pulling unresolved registry image: {reference}")

    result = run(
        ["docker", "pull", reference],
        check=False,
    )

    if result.returncode != 0:
        print(result.stderr.strip())
        return False

    return True


def docker_version() -> str:
    result = run(
        ["docker", "version", "--format", "{{.Server.Version}}"],
        check=False,
    )

    return result.stdout.strip() if result.returncode == 0 else "unknown"


def compose_version() -> str:
    result = run(
        ["docker", "compose", "version", "--short"],
        check=False,
    )

    return result.stdout.strip() if result.returncode == 0 else "unknown"


lock_entries: dict[str, dict[str, str]] = {}
manifest_services: dict[str, dict[str, Any]] = {}
errors: list[str] = []

registry_count = 0
build_count = 0
local_count = 0

for service_name in sorted(services):
    service = services[service_name]
    configured_image = service.get("image")
    build_config = service.get("build")
    container_id = get_container_id(service_name)

    image_id: str | None = None
    repo_digests: list[str] = []
    image_inspection: dict[str, Any] | None = None

    if container_id:
        container = inspect_container(container_id)

        if container:
            image_id = container.get("Image")

    if image_id:
        image_inspection = inspect_image(image_id)

    if image_inspection is None and configured_image:
        image_inspection = inspect_image(configured_image)

    if image_inspection:
        image_id = image_inspection.get("Id") or image_id
        repo_digests = [
            item
            for item in image_inspection.get("RepoDigests") or []
            if isinstance(item, str) and "@sha256:" in item
        ]

    entry: dict[str, Any] = {
        "configured_image": configured_image,
        "container_id": container_id,
        "current_image_id": image_id,
        "build": build_config,
    }

    if build_config is not None:
        lock_entries[service_name] = {
            "pull_policy": "build",
        }

        entry["source_type"] = "local-build"
        entry["lock_policy"] = "build"
        build_count += 1

    elif configured_image and "@sha256:" in configured_image:
        lock_entries[service_name] = {
            "image": configured_image,
        }

        entry["source_type"] = "registry"
        entry["locked_image"] = configured_image
        entry["lock_policy"] = "digest"
        registry_count += 1

    elif configured_image:
        locked_image = choose_repo_digest(
            configured_image,
            repo_digests,
        )

        if locked_image is None:
            if image_inspection is None:
                if pull_image(configured_image):
                    image_inspection = inspect_image(configured_image)

                    if image_inspection:
                        image_id = image_inspection.get("Id")
                        repo_digests = [
                            item
                            for item in image_inspection.get("RepoDigests") or []
                            if isinstance(item, str) and "@sha256:" in item
                        ]

                        locked_image = choose_repo_digest(
                            configured_image,
                            repo_digests,
                        )

        if locked_image:
            lock_entries[service_name] = {
                "image": locked_image,
            }

            entry["source_type"] = "registry"
            entry["locked_image"] = locked_image
            entry["lock_policy"] = "digest"
            registry_count += 1

        elif image_id:
            lock_entries[service_name] = {
                "pull_policy": "never",
            }

            entry["source_type"] = "local-artifact"
            entry["lock_policy"] = "never-pull"
            entry["required_local_image"] = configured_image
            local_count += 1

        else:
            errors.append(
                f"{service_name}: image '{configured_image}' "
                "could not be resolved locally or from its registry"
            )

    else:
        errors.append(
            f"{service_name}: service has neither an image nor a build definition"
        )

    manifest_services[service_name] = entry

if errors:
    print()
    for error in errors:
        print(f"ERROR: {error}")

    raise SystemExit(
        f"ERROR: {len(errors)} service image(s) could not be locked."
    )

yaml_lines = [
    "# Generated by scripts/update-image-lock.sh",
    "# Registry images are immutable digest references.",
    "# Local builds are always built from repository sources.",
    "# Local artifacts must be provisioned before Compose starts.",
    "services:",
]

for service_name in sorted(lock_entries):
    values = lock_entries[service_name]

    yaml_lines.append(f"  {json.dumps(service_name)}:")

    if "image" in values:
        yaml_lines.append(
            f"    image: {json.dumps(values['image'])}"
        )

    if "pull_policy" in values:
        yaml_lines.append(
            f"    pull_policy: {json.dumps(values['pull_policy'])}"
        )

lock_path.write_text(
    "\n".join(yaml_lines).rstrip() + "\n",
    encoding="utf-8",
)

manifest = {
    "schema_version": 1,
    "generated_at": datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(),
    "project": project,
    "base_compose": base_compose.split(":"),
    "lock_file": "compose.images.lock.yaml",
    "docker_version": docker_version(),
    "docker_compose_version": compose_version(),
    "summary": {
        "total_services": len(services),
        "registry_digest_services": registry_count,
        "local_build_services": build_count,
        "local_artifact_services": local_count,
    },
    "services": manifest_services,
}

manifest_path.write_text(
    json.dumps(
        manifest,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)

summary_lines = [
    "AI Station Docker Image Lock",
    "============================",
    f"Total services: {len(services)}",
    f"Registry images pinned by digest: {registry_count}",
    f"Services built from repository: {build_count}",
    f"Required local image artifacts: {local_count}",
    "",
]

for service_name in sorted(manifest_services):
    service = manifest_services[service_name]
    source_type = service["source_type"]
    policy = service["lock_policy"]

    if source_type == "registry":
        detail = service.get("locked_image", "")
    elif source_type == "local-build":
        detail = "build from repository"
    else:
        detail = service.get("required_local_image", "")

    summary_lines.append(
        f"{service_name}: {source_type} | {policy} | {detail}"
    )

summary_path.write_text(
    "\n".join(summary_lines).rstrip() + "\n",
    encoding="utf-8",
)

print()
print(f"Registry digest services: {registry_count}")
print(f"Repository build services: {build_count}")
print(f"Local artifact services: {local_count}")
PY

echo
echo "Generated image lock:"

cat "$TEMP_DIR/$LOCK_FILE"

echo
echo "Validating merged locked configuration..."

COMPOSE_FILE="${BASE_COMPOSE}:${TEMP_DIR}/${LOCK_FILE}" \
    docker compose -p "$PROJECT" config --quiet

COMPOSE_FILE="${BASE_COMPOSE}:${TEMP_DIR}/${LOCK_FILE}" \
    docker compose -p "$PROJECT" config --no-path-resolution --format json \
    > "$TEMP_DIR/compose-locked.json"

python3 - \
    "$TEMP_DIR/compose-locked.json" \
    "$TEMP_DIR/image-lock.json" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys

config = json.loads(
    pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
)

manifest = json.loads(
    pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
)

services = config.get("services", {})
errors: list[str] = []

for name, lock_data in manifest["services"].items():
    resolved = services.get(name)

    if resolved is None:
        errors.append(f"{name}: missing from resolved Compose model")
        continue

    source_type = lock_data["source_type"]

    if source_type == "registry":
        image = resolved.get("image", "")

        if "@sha256:" not in image:
            errors.append(
                f"{name}: registry image is not digest-pinned"
            )

    elif source_type == "local-build":
        if resolved.get("pull_policy") != "build":
            errors.append(
                f"{name}: local build does not use pull_policy=build"
            )

    elif source_type == "local-artifact":
        if resolved.get("pull_policy") != "never":
            errors.append(
                f"{name}: local artifact does not use pull_policy=never"
            )

if errors:
    for error in errors:
        print(f"ERROR: {error}")

    raise SystemExit(
        f"ERROR: {len(errors)} image-lock validation error(s)."
    )

print("OK: All image lock policies are valid.")
PY

mv "$TEMP_DIR/$LOCK_FILE" "$ROOT/$LOCK_FILE"
mv "$TEMP_DIR/image-lock.json" "$ROOT/$MANIFEST_FILE"
mv "$TEMP_DIR/image-lock-summary.txt" "$ROOT/$SUMMARY_FILE"

chmod 0644 \
    "$ROOT/$LOCK_FILE" \
    "$ROOT/$MANIFEST_FILE" \
    "$ROOT/$SUMMARY_FILE"

cat > "$ROOT/$VERIFY_SCRIPT" <<'VERIFY'
#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="$ROOT/compose.images.lock.yaml"
MANIFEST_FILE="$ROOT/config/image-lock.json"

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
    '^COMPOSE_FILE=compose\.yml:compose\.hardening\.yaml:compose\.local-builds\.yaml:compose\.images\.lock\.yaml$' \
    .env; then
    echo "FAIL: .env does not activate the image lock."
    exit 1
fi

docker compose config --quiet
docker compose config --no-path-resolution --format json > /tmp/ai-station-locked-compose.json

python3 - \
    "$ROOT" \
    /tmp/ai-station-locked-compose.json \
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

        if not image_exists(resolved_image):
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
VERIFY

chmod +x "$ROOT/$VERIFY_SCRIPT"

cat > "$ROOT/$DOC_FILE" <<'EOF'
# Docker Image Lock

AI Station separates container images into three categories.

## Registry images

Registry-backed images are pinned using immutable SHA-256 digest references
inside `compose.images.lock.yaml`.

## Repository builds

Services that contain a Compose `build` definition use:

    pull_policy: build

They are built from the source and Dockerfile contained in the repository.

## Local image artifacts

Images created by provisioning scripts but not published to a registry use:

    pull_policy: never

The installer must build or provision those images before starting the
Compose project.

## Updating the lock

Run:

    ./scripts/update-image-lock.sh

Then execute:

    ./scripts/verify-image-lock.sh
    ./scripts/release-audit.sh

The image-lock file must be committed whenever an approved image version
changes.
EOF

chmod 0644 "$ROOT/$DOC_FILE"

# The updater is already stored in the repository.
chmod +x "$ROOT/scripts/update-image-lock.sh"

echo
echo "Activating image lock in .env and .env.example..."

python3 - "$ROOT/.env" "$ROOT/.env.example" <<'PY'
from pathlib import Path
import sys

new_value = (
    "COMPOSE_FILE="
    "compose.yml:"
    "compose.hardening.yaml:"
    "compose.local-builds.yaml:"
    "compose.images.lock.yaml"
)

for filename in sys.argv[1:]:
    path = Path(filename)

    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    output = []
    replaced = False

    for line in lines:
        if line.strip().startswith("COMPOSE_FILE="):
            if not replaced:
                output.append(new_value)
                replaced = True
            continue

        output.append(line)

    if not replaced:
        output.append("")
        output.append("# Ordered Docker Compose configuration")
        output.append(new_value)

    path.write_text(
        "\n".join(output).rstrip() + "\n",
        encoding="utf-8",
    )
PY

chmod 0600 "$ROOT/.env"
chmod 0644 "$ROOT/.env.example"

echo "OK: Image lock activated."

echo
echo "Integrating image-lock verification into release audit..."

python3 - "$ROOT/scripts/release-audit.sh" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

start = "# BEGIN IMAGE LOCK VALIDATION"
end = "# END IMAGE LOCK VALIDATION"

if start in text and end in text:
    before = text.split(start, 1)[0]
    after = text.split(end, 1)[1]
    text = before.rstrip() + "\n\n" + after.lstrip()

block = """# BEGIN IMAGE LOCK VALIDATION

if [[ -x scripts/verify-image-lock.sh ]]; then
    if scripts/verify-image-lock.sh; then
        pass "Docker image lock is valid"
    else
        fail "Docker image lock is invalid"
    fi
else
    fail "Docker image-lock verifier is missing"
fi

# END IMAGE LOCK VALIDATION

"""

marker = (
    "# ------------------------------------------------------------\n"
    "# Final result\n"
    "# ------------------------------------------------------------\n"
)

if marker not in text:
    raise SystemExit(
        "ERROR: Final-result marker was not found "
        "in scripts/release-audit.sh"
    )

text = text.replace(marker, block + marker, 1)

path.write_text(text, encoding="utf-8")
PY

chmod +x "$ROOT/scripts/release-audit.sh"

echo
echo "Validating final Compose configuration..."

docker compose config --quiet

echo "OK: Locked Compose configuration is valid."

echo
echo "Running image-lock verification..."

"$ROOT/scripts/verify-image-lock.sh"

echo
echo "Running runtime verification..."

"$ROOT/scripts/verify.sh"

echo
echo "Running final release audit..."

AUDIT_LOG="$TEMP_DIR/release-audit.log"

set +e
"$ROOT/scripts/release-audit.sh" 2>&1 | tee "$AUDIT_LOG"
AUDIT_EXIT="${PIPESTATUS[0]}"
set -e

if (( AUDIT_EXIT != 0 )); then
    echo "ERROR: Release audit failed."
    exit "$AUDIT_EXIT"
fi

ERRORS="$(
    sed -nE \
        's/^[[:space:]]*Errors:[[:space:]]*([0-9]+).*$/\1/p' \
        "$AUDIT_LOG" \
        | tail -n1
)"

WARNINGS="$(
    sed -nE \
        's/^[[:space:]]*Warnings:[[:space:]]*([0-9]+).*$/\1/p' \
        "$AUDIT_LOG" \
        | tail -n1
)"

if [[ "$ERRORS" != "0" || "$WARNINGS" != "0" ]]; then
    echo
    echo "ERROR: Release audit is not clean."
    echo "Errors:   ${ERRORS:-unknown}"
    echo "Warnings: ${WARNINGS:-unknown}"
    exit 1
fi

trap - ERR
rm -rf "$TEMP_DIR"

REGISTRY_COUNT="$(
    python3 -c \
        'import json; print(json.load(open("config/image-lock.json"))["summary"]["registry_digest_services"])'
)"

BUILD_COUNT="$(
    python3 -c \
        'import json; print(json.load(open("config/image-lock.json"))["summary"]["local_build_services"])'
)"

LOCAL_COUNT="$(
    python3 -c \
        'import json; print(json.load(open("config/image-lock.json"))["summary"]["local_artifact_services"])'
)"

echo
echo "============================================================"
echo " IMMUTABLE IMAGE LOCK COMPLETED"
echo "============================================================"
echo
echo "Registry images pinned by digest:"
echo "  $REGISTRY_COUNT"
echo
echo "Repository build services:"
echo "  $BUILD_COUNT"
echo
echo "Local image artifacts:"
echo "  $LOCAL_COUNT"
echo
echo "Compose configuration:"
grep '^COMPOSE_FILE=' .env
echo
echo "Release audit:"
echo "  Errors:   0"
echo "  Warnings: 0"
echo
echo "Backup:"
echo "  $BACKUP_DIR"
echo
echo "Git status:"
git status --short
echo
echo "No containers were restarted."
echo "No files were staged, committed, or pushed."
echo "============================================================"
