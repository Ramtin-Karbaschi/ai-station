#!/usr/bin/env bash
set -Eeuo pipefail

TARGET="/app/backend/data/cache/whisper/models/faster-whisper-large-v3"
REPO_ID="Systran/faster-whisper-large-v3"

echo "=== Provisioning ${REPO_ID} into Open WebUI persistent volume ==="
echo "Target inside container: ${TARGET}"
echo

docker exec -i ai-station-open-webui-1 sh -lc "mkdir -p '${TARGET}'"

for attempt in $(seq 1 40); do
  echo
  echo "=== Download attempt ${attempt}/40 ==="

  if [ "$attempt" -le 25 ]; then
    DISABLE_XET="0"
    echo "Mode: normal Hugging Face transfer"
  else
    DISABLE_XET="1"
    echo "Mode: fallback with HF_HUB_DISABLE_XET=1"
  fi

  if docker exec \
      -e HF_HUB_OFFLINE=0 \
      -e HF_HUB_DISABLE_TELEMETRY=1 \
      -e HF_HUB_DISABLE_UPDATE_CHECK=1 \
      -e HF_HUB_DOWNLOAD_TIMEOUT=180 \
      -e HF_HUB_ETAG_TIMEOUT=120 \
      -e HF_XET_NUM_CONCURRENT_RANGE_GETS=2 \
      -e HF_XET_RECONSTRUCT_WRITE_SEQUENTIALLY=1 \
      -e HF_HUB_DISABLE_XET="${DISABLE_XET}" \
      -i ai-station-open-webui-1 python - <<PY
from huggingface_hub import snapshot_download
from pathlib import Path

repo_id = "${REPO_ID}"
target = Path("${TARGET}")
target.mkdir(parents=True, exist_ok=True)

print("repo_id:", repo_id)
print("local_dir:", target)

path = snapshot_download(
    repo_id=repo_id,
    local_dir=str(target),
    local_files_only=False,
    max_workers=1,
    etag_timeout=120,
)

print("DONE:", path)
PY
  then
    echo
    echo "=== Download completed. Verifying required files... ==="

    docker exec -i ai-station-open-webui-1 sh -lc "
      set -e
      test -f '${TARGET}/config.json'
      test -f '${TARGET}/model.bin'
      test -f '${TARGET}/tokenizer.json'
      test -f '${TARGET}/preprocessor_config.json'
      echo 'Required files exist.'
      du -sh '${TARGET}'
      find '${TARGET}' -maxdepth 1 -type f -printf '%s  %f\n' | sort -nr
    "

    echo
    echo "=== Testing offline load ==="

    docker exec \
      -e HF_HUB_OFFLINE=1 \
      -e HF_HUB_DISABLE_TELEMETRY=1 \
      -i ai-station-open-webui-1 python - <<PY
from faster_whisper import WhisperModel

model_path = "${TARGET}"
print("Loading:", model_path)

model = WhisperModel(
    model_path,
    device="cpu",
    compute_type="int8",
    local_files_only=True,
)

print("OK: faster-whisper-large-v3 loaded offline from local path.")
PY

    echo
    echo "SUCCESS: Whisper large-v3 is provisioned locally."
    exit 0
  fi

  echo "Attempt failed. Keeping partial files and retrying after delay..."
  sleep 30
done

echo
echo "ERROR: Whisper large-v3 provisioning failed after all retries."
echo "Do not delete ${TARGET}. Re-run this script when internet is available."
exit 1
