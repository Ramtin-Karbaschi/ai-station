#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="/srv/ai-station"
PROFILE="core"
MODEL_IDS=()

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
        --id)
            MODEL_IDS+=("$2")
            shift 2
            ;;
        --help|-h)
            echo "Usage: verify-models.sh [--profile PROFILE] [--id MODEL_ID] [--data-root PATH]"
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

ARGS=(
    --manifest "$ROOT/config/model-manifest.json"
    --data-root "$DATA_ROOT"
    --profile "$PROFILE"
    --verify-only
)
for MODEL_ID in "${MODEL_IDS[@]}"; do
    ARGS+=(--id "$MODEL_ID")
done

exec "$VENV/bin/python" "$ROOT/scripts/model_provision.py" "${ARGS[@]}"
