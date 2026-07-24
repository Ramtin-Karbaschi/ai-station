#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="/srv/ai-station"
PROFILE="core"
HF_HUB_VERSION="1.24.0"

usage() {
    cat <<'EOF'
Usage:
  provision-models.sh [options]

Options:
  --profile core|all
  --data-root PATH
  --help

Examples:
  ./scripts/provision-models.sh --profile core
  ./scripts/provision-models.sh --profile all
EOF
}

while (( $# > 0 )); do
    case "$1" in
        --profile)
            PROFILE="$2"
            shift 2
            ;;
        --data-root)
            DATA_ROOT="$2"
            shift 2
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

if [[ "$PROFILE" != "core" && "$PROFILE" != "all" ]]; then
    echo "ERROR: Profile must be core or all."
    exit 2
fi

MANIFEST="$ROOT/config/model-manifest.json"
PYTHON_SCRIPT="$ROOT/scripts/model_provision.py"
VENV="$DATA_ROOT/runtime/hf-provisioner-venv"

if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: Model manifest is missing:"
    echo "       $MANIFEST"
    exit 1
fi

if [[ ! -f "$PYTHON_SCRIPT" ]]; then
    echo "ERROR: Model provisioner is missing:"
    echo "       $PYTHON_SCRIPT"
    exit 1
fi

mkdir -p \
    "$DATA_ROOT/runtime" \
    "$DATA_ROOT/cache/huggingface"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Creating Hugging Face provisioner environment..."

    if ! python3 -m venv "$VENV"; then
        if (( EUID == 0 )) \
            && command -v apt-get >/dev/null 2>&1; then

            apt-get update
            DEBIAN_FRONTEND=noninteractive \
                apt-get install -y python3-venv

            python3 -m venv "$VENV"
        else
            echo "ERROR: python3-venv is unavailable."
            echo "Install it and rerun this command."
            exit 1
        fi
    fi
fi

"$VENV/bin/python" -m pip \
    install \
    --disable-pip-version-check \
    --upgrade \
    "huggingface_hub==${HF_HUB_VERSION}"

exec "$VENV/bin/python" \
    "$PYTHON_SCRIPT" \
    --manifest "$MANIFEST" \
    --data-root "$DATA_ROOT" \
    --profile "$PROFILE"
