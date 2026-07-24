#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

INSTALL_ROOT="/opt/ai-station"
DATA_ROOT="/srv/ai-station"
MIN_FREE_GB=80
REQUIRE_GPU=true

usage() {
    cat <<'EOF'
Usage:
  preflight-install.sh [options]

Options:
  --source PATH
  --install-root PATH
  --data-root PATH
  --min-free-gb NUMBER
  --no-gpu
  --help
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
        --min-free-gb)
            MIN_FREE_GB="$2"
            shift 2
            ;;
        --no-gpu)
            REQUIRE_GPU=false
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

ERRORS=0
WARNINGS=0

pass() {
    printf 'OK: %s\n' "$1"
}

warn() {
    printf 'WARNING: %s\n' "$1"
    WARNINGS=$((WARNINGS + 1))
}

fail() {
    printf 'FAIL: %s\n' "$1"
    ERRORS=$((ERRORS + 1))
}

echo "============================================================"
echo " AI Station - Installation preflight"
echo "============================================================"

if [[ "$(uname -s)" == "Linux" ]]; then
    pass "Linux environment detected"
else
    fail "Linux environment is required"
fi

if grep -Eiq \
    '(microsoft|wsl)' \
    /proc/version /proc/sys/kernel/osrelease \
    2>/dev/null; then
    pass "WSL environment detected"
else
    warn "Native Linux detected; Windows launcher features will not apply"
fi

for COMMAND in \
    bash \
    docker \
    git \
    openssl \
    python3 \
    rsync \
    curl
do
    if command -v "$COMMAND" >/dev/null 2>&1; then
        pass "Command available: $COMMAND"
    else
        fail "Required command is missing: $COMMAND"
    fi
done

if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        pass "Docker daemon is reachable"
    else
        fail "Docker daemon is not reachable"
    fi

    if docker compose version >/dev/null 2>&1; then
        pass "Docker Compose v2 is available"
    else
        fail "Docker Compose v2 is unavailable"
    fi
fi

if [[ "$REQUIRE_GPU" == "true" ]]; then
    if command -v nvidia-smi >/dev/null 2>&1; then
        if nvidia-smi >/dev/null 2>&1; then
            pass "NVIDIA GPU is visible in Linux/WSL"
        else
            fail "nvidia-smi exists but cannot access the GPU"
        fi
    else
        fail "nvidia-smi is unavailable"
    fi
else
    warn "GPU check was explicitly disabled"
fi

for REQUIRED_FILE in \
    compose.yml \
    compose.hardening.yaml \
    compose.local-builds.yaml \
    compose.images.lock.yaml \
    .env.example \
    scripts/verify.sh \
    scripts/verify-image-lock.sh \
    scripts/verify-build-lock.sh \
    config/model-manifest.json \
    scripts/model_provision.py \
    scripts/provision-models.sh \
    scripts/verify-models.sh \
    scripts/verify-model-manifest.sh
do
    if [[ -f "$SOURCE_DIR/$REQUIRED_FILE" ]]; then
        pass "Source file exists: $REQUIRED_FILE"
    else
        fail "Source file is missing: $REQUIRED_FILE"
    fi
done

DATA_PARENT="$DATA_ROOT"

while [[ ! -e "$DATA_PARENT" && "$DATA_PARENT" != "/" ]]; do
    DATA_PARENT="$(dirname "$DATA_PARENT")"
done

if [[ -d "$DATA_PARENT" ]]; then
    AVAILABLE_KB="$(
        df -Pk "$DATA_PARENT" \
            | awk 'NR == 2 {print $4}'
    )"

    REQUIRED_KB=$(( MIN_FREE_GB * 1024 * 1024 ))

    if (( AVAILABLE_KB >= REQUIRED_KB )); then
        AVAILABLE_GB=$(( AVAILABLE_KB / 1024 / 1024 ))
        pass "Free storage is sufficient: ${AVAILABLE_GB} GiB"
    else
        AVAILABLE_GB=$(( AVAILABLE_KB / 1024 / 1024 ))
        fail "Insufficient free storage: ${AVAILABLE_GB} GiB available; ${MIN_FREE_GB} GiB required"
    fi
else
    fail "Unable to determine storage capacity for $DATA_ROOT"
fi

if [[ "$INSTALL_ROOT" == "$DATA_ROOT" ]]; then
    fail "Application and persistent-data roots must be different"
else
    pass "Application and data roots are separated"
fi

echo
echo "Preflight summary:"
echo "  Errors:   $ERRORS"
echo "  Warnings: $WARNINGS"

if (( ERRORS > 0 )); then
    echo
    echo "INSTALLATION PREFLIGHT FAILED"
    exit 1
fi

echo
echo "INSTALLATION PREFLIGHT PASSED"
