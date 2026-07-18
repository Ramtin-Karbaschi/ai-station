#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

fail=0

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

check_url http://127.0.0.1:3000 "Open WebUI"
check_url http://127.0.0.1:8890/health "UI Gateway"
check_url http://127.0.0.1:9998/tika "Apache Tika"
check_url "http://127.0.0.1:8889/search?q=test&format=json" "SearXNG"
check_url http://127.0.0.1:8090/v1/models "Embedding Server"
check_url http://127.0.0.1:8082/v1/models "General Model Server"

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

exit "$fail"
