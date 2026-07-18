#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

./scripts/compose-ai-station.sh \
  --profile llm-general \
  --profile coder \
  --profile thinking \
  --profile vision \
  stop \
  llm-general \
  llm-coder \
  llm-thinking \
  vlm || true

echo "Heavy models stopped. Gateway, Open WebUI and embedder remain available."
