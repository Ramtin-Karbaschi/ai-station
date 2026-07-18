#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

./scripts/compose-ai-station.sh \
  --profile console \
  --profile llm-general \
  --profile coder \
  --profile thinking \
  --profile vision \
  --profile rag \
  --profile reranker \
  stop \
  open-webui \
  llm-general \
  llm-coder \
  llm-thinking \
  vlm \
  embedder \
  reranker \
  api \
  worker \
  redis \
  postgres || true

systemctl stop ai-station-gateway || true

echo "AI Station stopped."
