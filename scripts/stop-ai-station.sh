#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

./scripts/compose-ai-station.sh stop \
  open-webui \
  llm-general \
  embedder \
  searxng \
  tika \
  redis \
  postgres || true

systemctl stop ai-station-ui-gateway 2>/dev/null || true
systemctl stop ai-station-gateway 2>/dev/null || true

echo "AI Station stopped."
