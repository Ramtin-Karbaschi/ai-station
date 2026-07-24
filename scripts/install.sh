#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

INSTALL_ROOT="/opt/ai-station"
DATA_ROOT="/srv/ai-station"
START_SERVICES=true
VALIDATE_ONLY=false
SKIP_PREFLIGHT=false
SKIP_MODEL_CHECK=false
FORCE=false

usage() {
    cat <<'EOF'
Usage:
  sudo ./scripts/install.sh [options]

Options:
  --source PATH
  --install-root PATH
  --data-root PATH
  --prepare-only
  --validate-only
  --skip-preflight
  --skip-model-check
  --force
  --help

Normal installation:
  sudo ./scripts/install.sh

Validate without changing the system:
  ./scripts/install.sh --validate-only
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --source)
            SOURCE_DIR="$2"
            shift 2
            ;;
        --install-root)
            INSTALL_ROOT="$2"
            shift 2
            ;;
        --data-root)
            DATA_ROOT="$2"
            shift 2
            ;;
        --prepare-only)
            START_SERVICES=false
            shift
            ;;
        --validate-only)
            VALIDATE_ONLY=true
            START_SERVICES=false
            shift
            ;;
        --skip-preflight)
            SKIP_PREFLIGHT=true
            shift
            ;;
        --skip-model-check)
            SKIP_MODEL_CHECK=true
            shift
            ;;
        --force)
            FORCE=true
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1"
            usage
            exit 2
            ;;
    esac
done

SOURCE_DIR="$(realpath "$SOURCE_DIR")"
INSTALL_ROOT="$(realpath -m "$INSTALL_ROOT")"
DATA_ROOT="$(realpath -m "$DATA_ROOT")"

EXPECTED_COMPOSE_FILE="$(
    printf '%s' \
        'compose.yml:compose.hardening.yaml:' \
        'compose.local-builds.yaml:compose.images.lock.yaml'
)"

echo "============================================================"
echo " AI Station - Installer"
echo "============================================================"
echo
echo "Source:"
echo "  $SOURCE_DIR"
echo
echo "Installation root:"
echo "  $INSTALL_ROOT"
echo
echo "Persistent data root:"
echo "  $DATA_ROOT"

for REQUIRED_FILE in \
    compose.yml \
    compose.hardening.yaml \
    compose.local-builds.yaml \
    compose.images.lock.yaml \
    .env.example \
    scripts/preflight-install.sh \
    scripts/verify-build-lock.sh \
    scripts/verify-image-lock.sh \
    scripts/verify.sh \
    config/model-manifest.json \
    scripts/model_provision.py \
    scripts/provision-models.sh \
    scripts/verify-models.sh \
    scripts/verify-model-manifest.sh
do
    if [[ ! -f "$SOURCE_DIR/$REQUIRED_FILE" ]]; then
        echo "ERROR: Required source file is missing:"
        echo "       $REQUIRED_FILE"
        exit 1
    fi
done

"$SOURCE_DIR/scripts/verify-build-lock.sh"

if [[ "$VALIDATE_ONLY" == "true" ]]; then
    if [[ "$SKIP_PREFLIGHT" != "true" ]]; then
        "$SOURCE_DIR/scripts/preflight-install.sh" \
            --source "$SOURCE_DIR" \
            --install-root "$INSTALL_ROOT" \
            --data-root "$DATA_ROOT"
    fi

    echo
    echo "INSTALLER VALIDATION PASSED"
    exit 0
fi

if (( EUID != 0 )); then
    echo "ERROR: Installation requires root privileges."
    echo "Run:"
    echo "  sudo ./scripts/install.sh"
    exit 1
fi

install_base_packages() {
    local missing=()

    for command in \
        curl \
        git \
        openssl \
        python3 \
        rsync
    do
        if ! command -v "$command" >/dev/null 2>&1; then
            missing+=("$command")
        fi
    done

    if (( ${#missing[@]} == 0 )); then
        return 0
    fi

    if command -v apt-get >/dev/null 2>&1; then
        echo
        echo "Installing required base packages..."

        apt-get update

        DEBIAN_FRONTEND=noninteractive \
            apt-get install -y \
                ca-certificates \
                curl \
                git \
                openssl \
                python3 \
                rsync
    else
        echo "ERROR: Missing commands: ${missing[*]}"
        echo "Automatic package installation supports apt-based systems only."
        exit 1
    fi
}

install_base_packages

if [[ "$SKIP_PREFLIGHT" != "true" ]]; then
    "$SOURCE_DIR/scripts/preflight-install.sh" \
        --source "$SOURCE_DIR" \
        --install-root "$INSTALL_ROOT" \
        --data-root "$DATA_ROOT"
fi

mkdir -p \
    "$DATA_ROOT/backups" \
    "$DATA_ROOT/cache" \
    "$DATA_ROOT/logs" \
    "$DATA_ROOT/models/general" \
    "$DATA_ROOT/models/coder" \
    "$DATA_ROOT/models/embedding" \
    "$DATA_ROOT/models/reranker" \
    "$DATA_ROOT/models/ocr" \
    "$DATA_ROOT/models/vision" \
    "$DATA_ROOT/models/whisper" \
    "$DATA_ROOT/runtime" \
    "$DATA_ROOT/support"

chmod 0755 "$DATA_ROOT"
chmod 0700 "$DATA_ROOT/backups"

if [[ "$SOURCE_DIR" != "$INSTALL_ROOT" ]]; then
    if [[ -d "$INSTALL_ROOT" ]] \
        && [[ -n "$(find "$INSTALL_ROOT" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then

        BACKUP_STAMP="$(date +%Y%m%d-%H%M%S)"
        UPGRADE_BACKUP="$DATA_ROOT/backups/installer-upgrade-${BACKUP_STAMP}.tar.gz"

        echo
        echo "Backing up existing installation..."

        tar \
            -C "$INSTALL_ROOT" \
            -czf "$UPGRADE_BACKUP" \
            .

        chmod 0600 "$UPGRADE_BACKUP"

        echo "Backup:"
        echo "  $UPGRADE_BACKUP"
    fi

    mkdir -p "$INSTALL_ROOT"

    echo
    echo "Deploying repository files..."

    rsync -a \
        --delete \
        --exclude='.git/' \
        --exclude='.env' \
        --exclude='_archive/' \
        --exclude='backups/' \
        --exclude='data/' \
        --exclude='logs/' \
        --exclude='models/' \
        --exclude='support/' \
        "$SOURCE_DIR/" \
        "$INSTALL_ROOT/"
else
    echo
    echo "Source already equals installation root; deployment copy skipped."
fi

cd "$INSTALL_ROOT"

if [[ ! -f .env ]]; then
    cp .env.example .env
fi

python3 - ".env" "$EXPECTED_COMPOSE_FILE" <<'PY'
from __future__ import annotations

import pathlib
import re
import secrets
import sys

path = pathlib.Path(sys.argv[1])
compose_value = sys.argv[2]

lines = path.read_text(encoding="utf-8").splitlines()
output = []
compose_written = False

secret_pattern = re.compile(
    r"(PASSWORD|SECRET)",
    re.IGNORECASE,
)

for line in lines:
    stripped = line.strip()

    if not stripped or stripped.startswith("#") or "=" not in line:
        output.append(line)
        continue

    key, value = line.split("=", 1)
    key = key.strip()

    if key == "COMPOSE_FILE":
        if not compose_written:
            output.append(
                f"COMPOSE_FILE={compose_value}"
            )
            compose_written = True
        continue

    if not value.strip() and secret_pattern.search(key):
        value = secrets.token_urlsafe(36)

    output.append(f"{key}={value}")

if not compose_written:
    output.append("")
    output.append(
        f"COMPOSE_FILE={compose_value}"
    )

path.write_text(
    "\n".join(output).rstrip() + "\n",
    encoding="utf-8",
)
PY

chmod 0600 .env

if ! grep -Fxq \
    "COMPOSE_FILE=$EXPECTED_COMPOSE_FILE" \
    .env; then
    echo "ERROR: Installer could not activate the Compose chain."
    exit 1
fi

echo
echo "Validating Compose configuration..."

docker compose config --quiet

./scripts/verify-build-lock.sh
./scripts/verify-image-lock.sh

echo
echo "Pulling immutable registry images..."

docker compose pull --ignore-buildable

echo
echo "Building repository-controlled images..."

docker compose build

# BEGIN AUTOMATIC MODEL PROVISIONING

if [[ "$SKIP_MODEL_CHECK" != "true" ]]; then
    echo
    echo "Provisioning required Core models..."

    "$INSTALL_ROOT/scripts/provision-models.sh" \
        --profile core \
        --data-root "$DATA_ROOT"

    echo
    echo "Verifying required Core models..."

    "$INSTALL_ROOT/scripts/verify-models.sh" \
        --profile core \
        --data-root "$DATA_ROOT"
fi

# END AUTOMATIC MODEL PROVISIONING

if [[ "$SKIP_MODEL_CHECK" != "true" ]]; then
    echo
    echo "Checking model bind mounts..."

    docker compose config \
        --no-path-resolution \
        --format json \
        > /tmp/ai-station-install-compose.json

    python3 - \
        /tmp/ai-station-install-compose.json \
        "$DATA_ROOT" <<'PY'
from __future__ import annotations

import json
import pathlib
import sys

config = json.loads(
    pathlib.Path(sys.argv[1]).read_text(
        encoding="utf-8"
    )
)

data_root = pathlib.Path(sys.argv[2]).resolve()
models_root = data_root / "models"

required_sources = set()

for service in config.get("services", {}).values():
    for volume in service.get("volumes") or []:
        if not isinstance(volume, dict):
            continue

        if volume.get("type") != "bind":
            continue

        source_value = volume.get("source")

        if not isinstance(source_value, str):
            continue

        source = pathlib.Path(source_value)

        if not source.is_absolute():
            continue

        try:
            source.resolve().relative_to(models_root)
        except ValueError:
            continue

        required_sources.add(source.resolve())

missing = []

for source in sorted(required_sources):
    if not source.exists():
        missing.append(
            f"{source}: missing"
        )
        continue

    if source.is_file() and source.stat().st_size == 0:
        missing.append(
            f"{source}: empty file"
        )

if missing:
    print()
    print("Required model artifacts are not ready:")

    for item in missing:
        print(f"  - {item}")

    print()
    print(
        "Provision the model pack before starting "
        "AI Station, or rerun with --skip-model-check "
        "only for infrastructure testing."
    )

    raise SystemExit(1)

print(
    "OK: Required model bind mounts are present: "
    f"{len(required_sources)}"
)
PY
fi

if [[ "$START_SERVICES" == "true" ]]; then
    echo
    echo "Starting AI Station..."

    docker compose up -d --remove-orphans

    echo
    echo "Waiting for service health..."

    for ATTEMPT in $(seq 1 90); do
        if ./scripts/verify.sh >/tmp/ai-station-install-verify.log 2>&1; then
            cat /tmp/ai-station-install-verify.log
            echo
            echo "AI STATION INSTALLATION PASSED"
            exit 0
        fi

        printf '\rVerification attempt %02d/90' "$ATTEMPT"
        sleep 2
    done

    echo
    echo "ERROR: AI Station did not pass verification."

    cat /tmp/ai-station-install-verify.log || true

    docker compose ps
    exit 1
fi

echo
echo "AI STATION PREPARATION PASSED"
echo
echo "Services were not started."
