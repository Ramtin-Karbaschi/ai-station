#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="/srv/ai-station"
PROFILE="core"

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
            echo "Usage: verify-models.sh [--profile core|all] [--data-root PATH]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1"
            exit 2
            ;;
    esac
done

VENV="$DATA_ROOT/runtime/hf-provisioner-venv"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "ERROR: Model provisioner environment is missing."
    echo "Run:"
    echo "  ./scripts/provision-models.sh --profile $PROFILE"
    exit 1
fi

exec "$VENV/bin/python" \
    "$ROOT/scripts/model_provision.py" \
    --manifest "$ROOT/config/model-manifest.json" \
    --data-root "$DATA_ROOT" \
    --profile "$PROFILE" \
    --verify-only
