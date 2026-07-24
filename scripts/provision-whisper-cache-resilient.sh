#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

MODEL_REPO="${1:-Systran/faster-whisper-small}"
WHISPER_MODEL_NAME="${2:-small}"
CACHE_DIR="/app/backend/data/cache/whisper/models"

echo "=== Whisper resilient provisioning ==="
echo "Repo:  ${MODEL_REPO}"
echo "Model: ${WHISPER_MODEL_NAME}"
echo "Cache: ${CACHE_DIR}"

echo
echo "=== Temporarily enabling Hugging Face online mode for Open WebUI ==="

cp -a compose.openwebui.override.yml "compose.openwebui.override.yml.bak-whisper-provision-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true

python3 - <<'PY'
from pathlib import Path
import re

p = Path("compose.openwebui.override.yml")
text = p.read_text()

def set_env(text, key, value):
    pattern = rf'^(\s*){re.escape(key)}:.*$'
    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, rf'\1{key}: {value}', text, flags=re.MULTILINE)

    marker = "    environment:\n"
    if marker not in text:
        raise SystemExit("environment block not found")
    return text.replace(marker, marker + f"      {key}: {value}\n", 1)

text = set_env(text, "HF_HUB_OFFLINE", '"0"')
text = set_env(text, "HF_HUB_DOWNLOAD_TIMEOUT", '"600"')
text = set_env(text, "HF_HUB_ETAG_TIMEOUT", '"120"')
text = set_env(text, "HF_HUB_ENABLE_HF_TRANSFER", '"0"')
text = set_env(text, "HF_HUB_DISABLE_XET", '"1"')

text = set_env(text, "WHISPER_MODEL", '"small"')
text = set_env(text, "WHISPER_MODEL_DIR", '"/app/backend/data/cache/whisper/models"')
text = set_env(text, "WHISPER_COMPUTE_TYPE", '"int8"')
text = set_env(text, "WHISPER_MULTILINGUAL", '"True"')
text = set_env(text, "WHISPER_LANGUAGE", '""')
text = set_env(text, "WHISPER_MODEL_AUTO_UPDATE", '"False"')

p.write_text(text)
PY

./scripts/compose-ai-station.sh \
  --profile console \
  --profile rag \
  --profile search \
  --profile tika \
  --profile llm-general \
  up -d --force-recreate open-webui

sleep 35

echo
echo "=== Downloading with retry/resume inside Open WebUI volume ==="

docker exec \
  -e HF_HUB_OFFLINE=0 \
  -e HF_HUB_DOWNLOAD_TIMEOUT=600 \
  -e HF_HUB_ETAG_TIMEOUT=120 \
  -e HF_HUB_ENABLE_HF_TRANSFER=0 \
  -e HF_HUB_DISABLE_XET=1 \
  -e MODEL_REPO="${MODEL_REPO}" \
  -e CACHE_DIR="${CACHE_DIR}" \
  -i ai-station-open-webui-1 python - <<'PY'
import os
import time
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

repo = os.environ["MODEL_REPO"]
cache_dir = Path(os.environ["CACHE_DIR"])
cache_dir.mkdir(parents=True, exist_ok=True)

print(f"repo={repo}")
print(f"cache_dir={cache_dir}")

# Stale locks can remain after power/network interruption.
locks = list(cache_dir.rglob("*.lock"))
if locks:
    print(f"Removing stale lock files: {len(locks)}")
    for lock in locks:
        try:
            lock.unlink()
        except Exception as e:
            print("Could not remove lock:", lock, repr(e))

attempts = 200
sleep_seconds = 20

for attempt in range(1, attempts + 1):
    print(f"\nDownload attempt {attempt}/{attempts}")

    try:
        path = snapshot_download(
            repo_id=repo,
            repo_type="model",
            cache_dir=str(cache_dir),
            local_files_only=False,
            force_download=False,
            max_workers=1,
        )

        print("\nOK: snapshot ready")
        print(path)

        files = list(Path(path).rglob("*"))
        print(f"snapshot files/dirs: {len(files)}")
        raise SystemExit(0)

    except KeyboardInterrupt:
        raise

    except Exception as e:
        print("FAILED:", repr(e))
        print(f"Sleeping {sleep_seconds}s before retry...")
        time.sleep(sleep_seconds)

print("ERROR: all attempts failed")
raise SystemExit(1)
PY

echo
echo "=== Verifying offline load ==="

docker exec \
  -e HF_HUB_OFFLINE=1 \
  -e WHISPER_MODEL_DIR="${CACHE_DIR}" \
  -i ai-station-open-webui-1 python - <<PY
from faster_whisper import WhisperModel

print("Loading ${WHISPER_MODEL_NAME} offline...")
model = WhisperModel(
    "${WHISPER_MODEL_NAME}",
    device="cpu",
    compute_type="int8",
    download_root="${CACHE_DIR}",
    local_files_only=True,
)
print("OK: Whisper loaded offline.")
PY

echo
echo "=== Locking Open WebUI back to offline mode ==="

python3 - <<'PY'
from pathlib import Path
import re

p = Path("compose.openwebui.override.yml")
text = p.read_text()

def set_env(text, key, value):
    pattern = rf'^(\s*){re.escape(key)}:.*$'
    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, rf'\1{key}: {value}', text, flags=re.MULTILINE)

    marker = "    environment:\n"
    return text.replace(marker, marker + f"      {key}: {value}\n", 1)

text = set_env(text, "HF_HUB_OFFLINE", '"1"')
text = set_env(text, "WHISPER_MODEL_AUTO_UPDATE", '"False"')
text = set_env(text, "WHISPER_MODEL", '"small"')
text = set_env(text, "WHISPER_MODEL_DIR", '"/app/backend/data/cache/whisper/models"')
text = set_env(text, "WHISPER_COMPUTE_TYPE", '"int8"')
text = set_env(text, "WHISPER_MULTILINGUAL", '"True"')
text = set_env(text, "WHISPER_LANGUAGE", '""')

p.write_text(text)
PY

./scripts/compose-ai-station.sh \
  --profile console \
  --profile rag \
  --profile search \
  --profile tika \
  --profile llm-general \
  up -d --force-recreate open-webui

sleep 35

echo
echo "=== Final cache size ==="
docker exec -i ai-station-open-webui-1 sh -lc '
du -sh /app/backend/data/cache/whisper/models || true
find /app/backend/data/cache/whisper/models -maxdepth 4 -type f | sed -n "1,50p"
'

echo
echo "DONE: Whisper cache provisioned and locked offline."
