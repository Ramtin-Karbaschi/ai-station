#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-open-webui}"

case "$TARGET" in
  open-webui) docker logs -f ai-station-open-webui-1 ;;
  tika) docker logs -f ai-station-tika ;;
  searxng) docker logs -f ai-station-searxng ;;
  general) ./scripts/compose-ai-station.sh logs -f llm-general ;;
  embedder) ./scripts/compose-ai-station.sh logs -f embedder ;;
  gateway) journalctl -u ai-station-gateway -f --no-pager ;;
  ui-gateway) journalctl -u ai-station-ui-gateway -f --no-pager ;;
  *) echo "Usage: $0 {open-webui|tika|searxng|general|embedder|gateway|ui-gateway}"; exit 2 ;;
esac
