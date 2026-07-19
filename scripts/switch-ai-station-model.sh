#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-}"
cd /opt/ai-station

COMPOSE=(./scripts/compose-ai-station.sh)

wait_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-360}"

  echo "Waiting for $label ..."
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      echo "$label is ready."
      return 0
    fi
    sleep 2
  done

  echo "ERROR: $label did not become ready."
  return 1
}

case "$MODE" in
  general)
    SERVICE="llm-general"
    PORT="8082"
    MODEL="ai-station-general"
    ;;
  *)
    echo "Usage: $0 general"
    echo
    echo "Verified baseline currently exposes only the general LLM runtime."
    echo "Coder and reranker weights may be provisioned, but are not Compose-active."
    exit 2
    ;;
esac

sudo systemctl start docker >/dev/null 2>&1 || true

echo "Ensuring core stack is running..."
"${COMPOSE[@]}" up -d postgres redis searxng tika embedder open-webui

wait_url "http://127.0.0.1:3000" "Open WebUI" 240
wait_url "http://127.0.0.1:8090/v1/models" "Embedding backend" 240

echo "Starting selected model: $MODE"
"${COMPOSE[@]}" up -d "$SERVICE"

wait_url "http://127.0.0.1:${PORT}/v1/models" "$MODEL" 480

echo
echo "AI Station model switched successfully."
echo "Active mode: $MODE"
echo "Model:       $MODEL"
echo "Model API:   http://127.0.0.1:${PORT}/v1"
echo "UI:          http://127.0.0.1:3000"
