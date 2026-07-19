#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

echo "=== Docker Compose Services ==="
./scripts/compose-ai-station.sh ps

echo
echo "=== HTTP Checks ==="
for item in \
  "Open WebUI|http://127.0.0.1:3000" \
  "UI Gateway|http://127.0.0.1:8890/health" \
  "Gateway|http://127.0.0.1:8888/health" \
  "General|http://127.0.0.1:8082/v1/models" \
  "Embedding|http://127.0.0.1:8090/v1/models" \
  "SearXNG|http://127.0.0.1:8889/search?q=test&format=json" \
  "Tika|http://127.0.0.1:9998/tika"
do
  name="${item%%|*}"
  url="${item#*|}"

  if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
    echo "OK   $name"
  else
    echo "DOWN $name"
  fi
done

echo
echo "=== GPU ==="
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv 2>/dev/null || true

echo
echo "=== Disk ==="
df -h / /srv/ai-station/models 2>/dev/null || df -h /
