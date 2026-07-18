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
    PROFILE="llm-general"
    SERVICE="llm-general"
    PORT="8082"
    MODEL="ai-station-general"
    ;;
  coder)
    PROFILE="coder"
    SERVICE="llm-coder"
    PORT="8083"
    MODEL="ai-station-coder"
    ;;
  thinking)
    PROFILE="thinking"
    SERVICE="llm-thinking"
    PORT="8084"
    MODEL="ai-station-thinking"
    ;;
  vision)
    PROFILE="vision"
    SERVICE="vlm"
    PORT="8085"
    MODEL="ai-station-vision"
    ;;
  *)
    echo "Usage: $0 {general|coder|thinking|vision}"
    exit 2
    ;;
esac

sudo systemctl start docker >/dev/null 2>&1 || true

echo "Ensuring core services are running..."
"${COMPOSE[@]}" up -d postgres redis api worker

echo "Ensuring Open WebUI and local embedding are running..."
"${COMPOSE[@]}" --profile console --profile rag up -d open-webui embedder

wait_url "http://127.0.0.1:3000" "Open WebUI" 240
wait_url "http://127.0.0.1:8090/v1/models" "Embedding backend" 240

echo "Stopping other heavy models..."
"${COMPOSE[@]}" \
  --profile llm-general \
  --profile coder \
  --profile thinking \
  --profile vision \
  stop \
  llm-general \
  llm-coder \
  llm-thinking \
  vlm >/dev/null 2>&1 || true

echo "Starting selected model: $MODE"
"${COMPOSE[@]}" --profile "$PROFILE" up -d "$SERVICE"

wait_url "http://127.0.0.1:${PORT}/v1/models" "$MODEL" 480

echo
echo "AI Station model switched successfully."
echo "Active mode: $MODE"
echo "Model:       $MODEL"
echo "Model API:   http://localhost:${PORT}/v1"
echo "UI:          http://localhost:3000"
echo
echo "In Open WebUI: refresh the page if the new model is not visible immediately."
