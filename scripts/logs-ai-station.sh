#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="${1:-open-webui}"

cd /opt/ai-station

case "$TARGET" in
  webui|open-webui)
    SERVICE="open-webui" ;;
  general)
    SERVICE="llm-general" ;;
  embedding|embedder)
    SERVICE="embedder" ;;
  tika)
    SERVICE="tika" ;;
  searxng)
    SERVICE="searxng" ;;
  postgres)
    SERVICE="postgres" ;;
  redis)
    SERVICE="redis" ;;
  *)
    echo "Usage: $0 {open-webui|general|embedder|tika|searxng|postgres|redis}"
    exit 2 ;;
esac

./scripts/compose-ai-station.sh logs -f --tail=200 "$SERVICE"
