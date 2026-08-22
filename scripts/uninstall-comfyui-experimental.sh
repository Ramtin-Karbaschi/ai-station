#!/usr/bin/env bash
# Uninstall the experimental ComfyUI media profile and (optionally) quarantine weights.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Stopping experimental ComfyUI profile..."
docker compose -f compose.yml -f compose.comfyui.experimental.yaml \
  --profile comfyui-experimental stop comfyui-experimental 2>/dev/null || true
docker compose -f compose.yml -f compose.comfyui.experimental.yaml \
  --profile comfyui-experimental rm -f comfyui-experimental 2>/dev/null || true

if [[ "${1:-}" == "--remove-weights" ]]; then
  TARGET="/srv/ai-station/models/comfyui"
  if [[ -d "$TARGET" ]]; then
    STAMP="$(date -u +%Y%m%d-%H%M%S)"
    DEST="/srv/ai-station/quarantine/${STAMP}-comfyui-media"
    mkdir -p /srv/ai-station/quarantine
    mv "$TARGET" "$DEST"
    echo "Moved weights to $DEST"
  fi
fi

echo "Experimental ComfyUI uninstalled from the active runtime."
echo "Restore a production chat model with: ai models use coder"
