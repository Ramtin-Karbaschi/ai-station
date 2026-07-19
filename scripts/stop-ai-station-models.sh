#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

./scripts/compose-ai-station.sh stop llm-general || true

echo "Heavy models stopped. Gateway, Open WebUI and embedder remain available."
