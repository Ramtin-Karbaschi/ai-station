#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -x "$ROOT/scripts/compose-ai-station.sh" ]]; then
  "$ROOT/scripts/compose-ai-station.sh" stop \
    open-webui llm-general embedder searxng tika redis postgres || true
else
  echo "WARNING: compose helper missing; stopping known containers directly."
  docker stop \
    ai-station-open-webui-1 \
    ai-station-llm-general-1 \
    ai-station-embedder-1 \
    ai-station-searxng \
    ai-station-tika \
    ai-station-redis-1 \
    ai-station-postgres-1 2>/dev/null || true
fi

systemctl stop ai-station-ui-gateway 2>/dev/null || true
systemctl stop ai-station-gateway 2>/dev/null || true
echo "AI Station stopped."
