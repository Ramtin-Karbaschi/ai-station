#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

echo "=== Docker Compose Services ==="
./scripts/compose-ai-station.sh \
  --profile console \
  --profile llm-general \
  --profile coder \
  --profile thinking \
  --profile vision \
  --profile rag \
  --profile reranker \
  ps

echo
echo "=== HTTP Checks ==="
for item in \
  "Open WebUI|http://127.0.0.1:3000" \
  "API|http://127.0.0.1:8080/health" \
  "General|http://127.0.0.1:8082/v1/models" \
  "Coder|http://127.0.0.1:8083/v1/models" \
  "Thinking|http://127.0.0.1:8084/v1/models" \
  "Vision|http://127.0.0.1:8085/v1/models" \
  "Embedding|http://127.0.0.1:8090/v1/models"
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
df -h / /srv/ai-station/models
