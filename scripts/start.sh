#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

systemctl start docker
systemctl restart ai-station-gateway
systemctl restart ai-station-ui-gateway

./scripts/compose-ai-station.sh up -d postgres redis searxng tika embedder llm-general open-webui

wait_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-120}"
  echo "Waiting for ${label}..."
  for i in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 5 "$url" >/dev/null 2>&1; then
      echo "OK: ${label}"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: ${label} is not ready: ${url}"
  exit 1
}

wait_url http://127.0.0.1:8890/health "UI Gateway" 60
wait_url http://127.0.0.1:9998/tika "Apache Tika" 120
wait_url "http://127.0.0.1:8889/search?q=test&format=json" "SearXNG" 90
wait_url http://127.0.0.1:8090/v1/models "Embedding Server" 180
wait_url http://127.0.0.1:8082/v1/models "General Model Server" 300
wait_url http://127.0.0.1:3000 "Open WebUI" 180

echo
echo "AI Station is ready: http://127.0.0.1:3000"
