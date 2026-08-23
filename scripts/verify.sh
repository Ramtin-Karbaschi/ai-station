#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

fail=0
active_profile=""

check_url() {
  local url="$1"
  local label="$2"
  if curl -fsS --max-time 15 "$url" >/dev/null 2>&1; then
    echo "OK: $label"
  else
    echo "FAIL: $label ($url)"
    fail=1
  fi
}

if [[ -f /srv/ai-station/runtime/active-heavy-profile ]]; then
  active_profile="$(tr -d '[:space:]' </srv/ai-station/runtime/active-heavy-profile)"
fi

check_url http://127.0.0.1:3000 "Open WebUI"
check_url http://127.0.0.1:4000/health/liveliness "LiteLLM Gateway"
check_url http://127.0.0.1:8888/health "Host Gateway"
check_url http://127.0.0.1:8890/health "UI Gateway"
check_url http://127.0.0.1:9998/tika "Apache Tika"
check_url "http://127.0.0.1:8889/search?q=test&format=json" "SearXNG"
check_url http://127.0.0.1:8090/v1/models "Embedding Server"
check_url http://127.0.0.1:8091/v1/models "Reranker Server"

# Gateways must stay on loopback. The host gateway may additionally expose its
# TCP proxy on the exact docker0 bridge address so containers can reach the
# loopback-bound application without opening a wildcard or LAN listener.
assert_loopback_listener() {
  local port="$1"
  local label="$2"
  local allowed_bridge_host="${3:-}"
  local listeners
  listeners="$(ss -lntp 2>/dev/null | awk -v p=":${port}" '$4 ~ p {print $4}' || true)"
  if [[ -z "$listeners" ]]; then
    echo "FAIL: $label is not listening on port $port"
    fail=1
    return
  fi
  local line
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    if [[ "$line" == 127.0.0.1:* || "$line" == "[::1]:"* ]]; then
      continue
    fi
    if [[ -n "$allowed_bridge_host" && "$line" == "$allowed_bridge_host:$port" ]]; then
      continue
    fi
    echo "FAIL: $label listens on an unapproved address: $line"
    fail=1
    return
  done <<<"$listeners"
  echo "OK: $label approved binding"
}

docker_bridge_host="$(ip -4 -o addr show docker0 2>/dev/null | awk '{split($4, addr, "/"); print addr[1]; exit}' || true)"
assert_loopback_listener 4000 "LiteLLM Gateway"
assert_loopback_listener 8888 "Host Gateway" "$docker_bridge_host"
assert_loopback_listener 8890 "UI Gateway"

case "$active_profile" in
  general|"") check_url http://127.0.0.1:8082/v1/models "General Model Server" ;;
  coder) check_url http://127.0.0.1:8083/v1/models "Coder Model Server" ;;
  reasoning) check_url http://127.0.0.1:8084/v1/models "Reasoning Model Server" ;;
  vision) check_url http://127.0.0.1:8085/v1/models "Vision Model Server" ;;
  ornith) check_url http://127.0.0.1:8086/v1/models "Ornith Model Server" ;;
  qwen38) check_url http://127.0.0.1:8087/v1/models "Qwen3.8 Model Server" ;;
  longwriter) check_url http://127.0.0.1:8088/v1/models "LongWriter Model Server" ;;
  *)
    echo "FAIL: unknown active profile '$active_profile'"
    fail=1
    ;;
esac

docker exec -i ai-station-tika sh -lc 'tesseract --list-langs | grep -q fas' \
  && echo "OK: Persian OCR language pack" \
  || { echo "FAIL: Persian OCR language pack"; fail=1; }

docker exec -e HF_HUB_OFFLINE=1 -i ai-station-open-webui-1 python - <<'PY' \
  && echo "OK: local Whisper large-v3" \
  || { echo "FAIL: local Whisper large-v3"; exit 1; }
from faster_whisper import WhisperModel
WhisperModel(
    "/app/backend/data/cache/whisper/models/faster-whisper-large-v3",
    device="cpu",
    compute_type="int8",
    local_files_only=True,
)
PY

if docker network inspect ai-platform >/dev/null 2>&1; then
  echo "OK: ai-platform network"
else
  echo "FAIL: ai-platform network missing"
  fail=1
fi

exit "$fail"
