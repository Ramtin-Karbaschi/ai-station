#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

sudo systemctl start docker >/dev/null 2>&1 || true
sudo systemctl start ai-station-gateway >/dev/null 2>&1 || systemctl start ai-station-gateway || true

./scripts/compose-ai-station.sh up -d postgres redis api worker

./scripts/compose-ai-station.sh \
  --profile console \
  --profile rag \
  up -d open-webui embedder

echo "Waiting for Gateway..."
for i in $(seq 1 120); do
  if curl -fsS --max-time 2 http://127.0.0.1:8888/health >/dev/null 2>&1; then
    echo "Gateway is ready."
    break
  fi
  sleep 2
done

echo "Waiting for Open WebUI..."
for i in $(seq 1 180); do
  if curl -fsS --max-time 2 http://127.0.0.1:3000 >/dev/null 2>&1; then
    echo "Open WebUI is ready."
    break
  fi
  sleep 2
done

echo
echo "AI Station is ready."
echo "UI:      http://localhost:3000"
echo "Gateway: http://localhost:8888"
echo
echo "Select the model inside Open WebUI. The gateway will queue and route requests automatically."
