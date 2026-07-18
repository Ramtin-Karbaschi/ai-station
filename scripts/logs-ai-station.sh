#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="${1:-open-webui}"

cd /opt/ai-station

case "$TARGET" in
  webui|open-webui)
    SERVICE="open-webui" ;;
  general)
    SERVICE="llm-general" ;;
  coder)
    SERVICE="llm-coder" ;;
  thinking)
    SERVICE="llm-thinking" ;;
  vision)
    SERVICE="vlm" ;;
  embedding|embedder)
    SERVICE="embedder" ;;
  api)
    SERVICE="api" ;;
  worker)
    SERVICE="worker" ;;
  postgres)
    SERVICE="postgres" ;;
  redis)
    SERVICE="redis" ;;
  *)
    echo "Usage: $0 {open-webui|general|coder|thinking|vision|embedder|api|worker|postgres|redis}"
    exit 2 ;;
esac

./scripts/compose-ai-station.sh \
  --profile console \
  --profile llm-general \
  --profile coder \
  --profile thinking \
  --profile vision \
  --profile rag \
  --profile reranker \
  logs -f --tail=200 "$SERVICE"
