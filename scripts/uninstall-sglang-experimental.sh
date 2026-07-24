#!/usr/bin/env bash
# Uninstall the experimental SGLang profile and (optionally) its model snapshot.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Stopping experimental SGLang profile..."
docker compose -f compose.yml -f compose.sglang.experimental.yaml \
  --profile sglang-experimental stop sglang-experimental 2>/dev/null || true
docker compose -f compose.yml -f compose.sglang.experimental.yaml \
  --profile sglang-experimental rm -f sglang-experimental 2>/dev/null || true

if [[ "${1:-}" == "--remove-weights" ]]; then
  TARGET="/srv/ai-station/models/experimental/qwen3.6-35b-a3b-awq-4bit"
  if [[ -d "$TARGET" ]]; then
    STAMP="$(date -u +%Y%m%d-%H%M%S)"
    DEST="/srv/ai-station/quarantine/${STAMP}-qwen3.6-35b-a3b-awq-4bit"
    mkdir -p /srv/ai-station/quarantine
    mv "$TARGET" "$DEST"
    echo "Moved weights to $DEST"
  fi
fi

echo "Experimental SGLang uninstalled from the active runtime."
echo "Restore production general model with: ai models use general"
