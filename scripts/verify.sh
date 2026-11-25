#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

ROOT="$PWD"
AI_STATION_ROOT="$ROOT"
# shellcheck source=scripts/lib/ai-common.sh
source "$ROOT/scripts/lib/ai-common.sh"
# shellcheck source=scripts/lib/chat-readiness.sh
source "$ROOT/scripts/lib/chat-readiness.sh"

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

check_post_route_not_404() {
  local url="$1"
  local label="$2"
  local status
  status="$(curl -sS -o /dev/null -w "%{http_code}" --max-time 15 -X POST "$url" 2>/dev/null || true)"
  case "$status" in
    400|415|422)
      echo "OK: $label"
      ;;
    404|000|"")
      echo "FAIL: $label ($url returned ${status:-000})"
      fail=1
      ;;
    2*|3*)
        echo "OK: $label"
      ;;
    *)
      echo "FAIL: $label ($url returned $status)"
      fail=1
      ;;
  esac
}

active_profile="$(ai_active_heavy_profile || true)"
chat_max_tokens=128
runtime_mode=""
runtime_health_json="$(curl -fsS --max-time 5 http://127.0.0.1:8888/health 2>/dev/null || true)"
if [[ -n "$runtime_health_json" ]]; then
  runtime_mode="$(printf '%s' "$runtime_health_json" | python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, UnicodeDecodeError):
    payload = {}
print(payload.get("active_runtime_mode") or "")
' 2>/dev/null || true)"
fi
# Host /health is authoritative for the non-heavy CPU fallback.  A stale GPU
# marker must not send verification back to :8082 or trigger a new launch.
if [[ "$runtime_mode" == "cpu_fallback" ]]; then
  active_profile=""
fi
runtime_ready=0

case "$active_profile" in
  general) chat_model="Qwen3.8-27B-UD-Q4_K_M" ;;
  coder|ornith) chat_model="Ornith-1.5-35B-Q4_K_M" ;;
  reasoning)
    chat_model="Qwen3.8-27B-Reasoning-UD-Q4_K_M"
    chat_max_tokens=512
    ;;
  vision) chat_model="Qwen3.8-27B-Vision-UD-Q4_K_M" ;;
  qwen38) chat_model="Qwen3.8-27B-UD-Q4_K_M" ;;
  longwriter) chat_model="LongWriter-Zero-32B-Q4_K_M" ;;
  comfyui-experimental)
    echo "FAIL: no active chat model; ComfyUI is a media runtime"
    fail=1
    ;;
  "")
    if [[ "$runtime_mode" == "cpu_fallback" ]]; then
      chat_model="Qwen3.8-27B-UD-Q4_K_M"
      echo "Detected active bounded CPU chat runtime via host /health."
    else
      echo "FAIL: no active GPU or CPU chat runtime; verify will not launch one"
      fail=1
    fi
    ;;
  *)
    echo "FAIL: no chat canary mapping for active profile '$active_profile'"
    fail=1
    ;;
esac

check_url http://127.0.0.1:3000 "Open WebUI"
check_url http://127.0.0.1:4000/health/liveliness "LiteLLM Gateway"
check_url http://127.0.0.1:8888/health "Host Gateway"
check_url http://127.0.0.1:8890/health "UI Gateway"
check_url http://127.0.0.1:9998/tika "Apache Tika"
check_url "http://127.0.0.1:8889/search?q=test&format=json" "SearXNG"
check_url http://127.0.0.1:8090/v1/models "Embedding Server"
check_url http://127.0.0.1:8091/v1/models "Reranker Server"
check_url http://127.0.0.1:8092/v1/models "Qwen3-ASR"
check_post_route_not_404 http://127.0.0.1:8888/v1/audio/transcriptions "Host Gateway unified STT route"

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
  general)
    check_url http://127.0.0.1:8082/v1/models "General Model Server" && runtime_ready=1
    ;;
  coder) check_url http://127.0.0.1:8083/v1/models "Coder Model Server" && runtime_ready=1 ;;
  reasoning) check_url http://127.0.0.1:8084/v1/models "Reasoning Model Server" && runtime_ready=1 ;;
  vision) check_url http://127.0.0.1:8085/v1/models "Vision Model Server" && runtime_ready=1 ;;
  ornith) check_url http://127.0.0.1:8086/v1/models "Ornith Model Server" && runtime_ready=1 ;;
  qwen38) check_url http://127.0.0.1:8087/v1/models "Qwen3.8 Model Server" && runtime_ready=1 ;;
  longwriter) check_url http://127.0.0.1:8088/v1/models "LongWriter Model Server" && runtime_ready=1 ;;
  "")
    if [[ "$runtime_mode" == "cpu_fallback" ]] \
      && check_url http://127.0.0.1:8089/v1/models "Bounded CPU Chat Model Server"; then
      runtime_ready=1
    elif [[ "$runtime_mode" == "cpu_fallback" ]]; then
      echo "FAIL: active CPU runtime is not management-ready; no public generation attempted"
    fi
    ;;
  comfyui-experimental) check_url http://127.0.0.1:8188/system_stats "ComfyUI Media Server" ;;
  *)
    echo "FAIL: unknown active profile '$active_profile'"
    fail=1
    ;;
esac

if [[ -n "${chat_model:-}" && "$runtime_ready" == 1 ]]; then
  master_key="$(ai_master_key)"
  if ! ai_chat_generation_canary \
    "http://127.0.0.1:4000/v1/chat/completions" \
    "$chat_model" "$master_key" "LiteLLM public API" 2 45 true "$chat_max_tokens" false; then
    fail=1
    PYTHONPATH="$ROOT" python3 "$ROOT/scripts/lib/hardware_detect.py" detect --json \
      | python3 -c 'import json,sys; report=json.load(sys.stdin); print("Current WSL GPU visibility: " + report["runtime_gpu"]["message"] + " (status=" + report["runtime_gpu"]["status"] + ").")' \
      || true
  fi
  unset master_key
elif [[ -n "${chat_model:-}" ]]; then
  echo "FAIL: no already-ready model runtime; verify will not launch an extra GPU or CPU service"
  fail=1
fi

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
