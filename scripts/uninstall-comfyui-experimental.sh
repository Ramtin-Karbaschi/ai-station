#!/usr/bin/env bash
# Stop the ComfyUI overlay. Weights are retained operator models and
# must never be deleted or quarantined (MiniMax Music 3 / H3 / FLUX.2).
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Stopping ComfyUI overlay (historical compose profile name)..."
docker compose -f compose.yml -f compose.comfyui.experimental.yaml \
  --profile comfyui-experimental stop comfyui-experimental 2>/dev/null || true
docker compose -f compose.yml -f compose.comfyui.experimental.yaml \
  --profile comfyui-experimental rm -f comfyui-experimental 2>/dev/null || true

if [[ "${1:-}" == "--remove-weights" ]]; then
  echo "ERROR: refusing --remove-weights. ComfyUI MiniMax Music 3, MiniMax H3, and FLUX.2 are retained operator models and must never be deleted or quarantined." >&2
  exit 1
fi

echo "ComfyUI overlay stopped. Weights stay on disk."
echo "Restore a chat model with: ai models use coder"
