#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

TS="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="/opt/ai-station/_archive/pre-finalize-${TS}"
mkdir -p "$ARCHIVE"

echo "=== AI Station Runtime Finalization ==="
echo "Archive: $ARCHIVE"

echo
echo "=== Backup current config ==="
cp -a \
  compose*.yml \
  .env* \
  scripts \
  apps \
  infra \
  config \
  "$ARCHIVE/" 2>/dev/null || true

echo
echo "=== Stop obsolete containers ==="
docker rm -f ai-station-docling 2>/dev/null || true
docker rm -f ai-station-open-webui-1 ai-station-llm-general-1 ai-station-searxng ai-station-tika 2>/dev/null || true

echo
echo "=== Validate required local images ==="
docker image inspect ghcr.io/open-webui/open-webui@sha256:a26effeb220e132482bf7e0560b3404843e7bc40d23051144e062960df8df6b0 >/dev/null
docker image inspect ghcr.io/ggml-org/llama.cpp:server-cuda >/dev/null
docker image inspect pgvector/pgvector:pg17 >/dev/null
docker image inspect redis:7-alpine >/dev/null
docker image inspect searxng/searxng:latest >/dev/null
docker image inspect ai-station/tika-fa:3.3.0.0-full >/dev/null

echo
echo "=== Create clean repo directories ==="
mkdir -p docs scripts infra/tika-fa infra/searxng secrets

echo
echo "=== Generate secrets if missing ==="
[ -f secrets/postgres_password.txt ] || openssl rand -hex 24 > secrets/postgres_password.txt
[ -f secrets/webui_secret_key.txt ] || openssl rand -hex 32 > secrets/webui_secret_key.txt
chmod 600 secrets/*.txt

POSTGRES_PASSWORD="$(cat secrets/postgres_password.txt)"
WEBUI_SECRET_KEY="$(cat secrets/webui_secret_key.txt)"

cat > .env.example <<'EOF'
# AI Station example environment.
# Copy this file to .env and adjust paths/models for your machine.

COMPOSE_PROJECT_NAME=ai-station
AI_STATION_NAME=AI Station

POSTGRES_DB=openwebui
POSTGRES_USER=openwebui

MODELS_DIR=/srv/ai-station/models

GENERAL_MODEL_FILE=general/qwen3.6-35b-a3b-ud-q4_k_m.gguf
EMBEDDING_MODEL_FILE=embedding/qwen3-embedding-0.6b-q8_0.gguf

GENERAL_CONTEXT=8192
EMBEDDING_CONTEXT=8192

WEBUI_PORT=3000
GATEWAY_PORT=8888
UI_GATEWAY_PORT=8890
SEARXNG_PORT=8889
TIKA_PORT=9998
GENERAL_LLM_PORT=8082
EMBEDDER_PORT=8090
EOF

cat > .env <<EOF
COMPOSE_PROJECT_NAME=ai-station
AI_STATION_NAME=AI Station

POSTGRES_DB=openwebui
POSTGRES_USER=openwebui

MODELS_DIR=/srv/ai-station/models

GENERAL_MODEL_FILE=general/qwen3.6-35b-a3b-ud-q4_k_m.gguf
EMBEDDING_MODEL_FILE=embedding/qwen3-embedding-0.6b-q8_0.gguf

GENERAL_CONTEXT=8192
EMBEDDING_CONTEXT=8192

WEBUI_PORT=3000
GATEWAY_PORT=8888
UI_GATEWAY_PORT=8890
SEARXNG_PORT=8889
TIKA_PORT=9998
GENERAL_LLM_PORT=8082
EMBEDDER_PORT=8090
EOF

echo
echo "=== Write canonical Docker Compose ==="
cat > compose.yml <<'YAML'
name: ai-station

services:
  postgres:
    image: pgvector/pgvector:pg17
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-openwebui}
      POSTGRES_USER: ${POSTGRES_USER:-openwebui}
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-openwebui} -d ${POSTGRES_DB:-openwebui}"]
      interval: 10s
      timeout: 5s
      retries: 20

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redisdata:/data
    ports:
      - "127.0.0.1:6379:6379"

  searxng:
    image: searxng/searxng:latest
    container_name: ai-station-searxng
    restart: unless-stopped
    environment:
      SEARXNG_BASE_URL: "http://127.0.0.1:${SEARXNG_PORT:-8889}/"
      UWSGI_WORKERS: "2"
      UWSGI_THREADS: "2"
    volumes:
      - ./infra/searxng:/etc/searxng:ro
    ports:
      - "127.0.0.1:${SEARXNG_PORT:-8889}:8080"

  tika:
    image: ai-station/tika-fa:3.3.0.0-full
    pull_policy: never
    container_name: ai-station-tika
    restart: unless-stopped
    environment:
      JAVA_TOOL_OPTIONS: "-Xms512m -Xmx3g -XX:+ExitOnOutOfMemoryError"
    ports:
      - "127.0.0.1:${TIKA_PORT:-9998}:9998"
    healthcheck:
      test: ["CMD-SHELL", "timeout 3 bash -lc '</dev/tcp/127.0.0.1/9998' || exit 1"]
      interval: 20s
      timeout: 5s
      retries: 10
      start_period: 30s

  embedder:
    image: ghcr.io/ggml-org/llama.cpp:server-cuda
    restart: unless-stopped
    gpus: all
    command:
      - -m
      - /models/${EMBEDDING_MODEL_FILE:-embedding/qwen3-embedding-0.6b-q8_0.gguf}
      - --alias
      - ai-station-embedding
      - --host
      - 0.0.0.0
      - --port
      - "8090"
      - -ngl
      - "999"
      - -c
      - "${EMBEDDING_CONTEXT:-8192}"
      - --embedding
      - --pooling
      - last
    volumes:
      - ${MODELS_DIR:-/srv/ai-station/models}:/models:ro
    ports:
      - "127.0.0.1:${EMBEDDER_PORT:-8090}:8090"
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8090/v1/models >/dev/null || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 20
      start_period: 60s

  llm-general:
    image: ghcr.io/ggml-org/llama.cpp:server-cuda
    restart: unless-stopped
    gpus: all
    command:
      - -m
      - /models/${GENERAL_MODEL_FILE:-general/qwen3.6-35b-a3b-ud-q4_k_m.gguf}
      - --alias
      - ai-station-general
      - --reasoning
      - "off"
      - --reasoning-budget
      - "0"
      - --host
      - 0.0.0.0
      - --port
      - "8082"
      - -ngl
      - "999"
      - -c
      - "${GENERAL_CONTEXT:-8192}"
      - --parallel
      - "1"
    volumes:
      - ${MODELS_DIR:-/srv/ai-station/models}:/models:ro
    ports:
      - "127.0.0.1:${GENERAL_LLM_PORT:-8082}:8082"
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://127.0.0.1:8082/v1/models >/dev/null || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 30
      start_period: 300s

  open-webui:
    image: ghcr.io/open-webui/open-webui@sha256:a26effeb220e132482bf7e0560b3404843e7bc40d23051144e062960df8df6b0
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      tika:
        condition: service_healthy
      embedder:
        condition: service_started
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      WEBUI_NAME: "AI Station"
      WEBUI_AUTH: "True"
      WEBUI_SECRET_KEY_FILE: /run/secrets/webui_secret_key
      WEBUI_URL: "http://localhost:${WEBUI_PORT:-3000}"

      DATABASE_URL: "postgresql://${POSTGRES_USER:-openwebui}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-openwebui}"
      VECTOR_DB: "pgvector"
      PGVECTOR_DB_URL: "postgresql://${POSTGRES_USER:-openwebui}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-openwebui}"
      REDIS_URL: "redis://redis:6379/0"
      WEBSOCKET_MANAGER: "redis"
      ENABLE_WEBSOCKET_SUPPORT: "true"

      ENABLE_OPENAI_API: "True"
      ENABLE_OLLAMA_API: "False"
      OPENAI_API_BASE_URLS: "http://host.docker.internal:8890/v1"
      OPENAI_API_KEYS: "local-not-used"
      OPENAI_API_CONFIGS: '{"0": {"enable": true, "prefix_id": "", "model_ids": ["general-qwen3.6"], "tags": [], "connection_type": "openai"}}'

      ENABLE_PERSISTENT_CONFIG: "False"
      DEFAULT_MODELS: "general-qwen3.6"
      DEFAULT_PINNED_MODELS: "general-qwen3.6"
      DEFAULT_MODEL_METADATA: '{"capabilities": {"vision": true, "file_upload": true, "file_context": true, "web_search": true, "image_generation": false, "code_interpreter": false}}'
      DEFAULT_MODEL_PARAMS: '{"temperature": 0.2, "num_ctx": 8192, "max_tokens": 1024}'

      CONTENT_EXTRACTION_ENGINE: "tika"
      TIKA_SERVER_URL: "http://tika:9998"
      RAG_EMBEDDING_ENGINE: "openai"
      RAG_EMBEDDING_MODEL: "ai-station-embedding"
      RAG_OPENAI_API_BASE_URL: "http://embedder:8090/v1"
      RAG_OPENAI_API_KEY: "local-not-used"
      RAG_FILE_MAX_SIZE: "150"
      RAG_FILE_MAX_COUNT: "20"
      RAG_TEXT_SPLITTER: "token"
      CHUNK_SIZE: "512"
      CHUNK_OVERLAP: "64"
      RAG_TOP_K: "3"
      RAG_FULL_CONTEXT: "False"

      ENABLE_WEB_SEARCH: "True"
      ENABLE_SEARCH_QUERY_GENERATION: "True"
      WEB_SEARCH_ENGINE: "searxng"
      SEARXNG_QUERY_URL: "http://searxng:8080/search?q=<query>&format=json"
      WEB_SEARCH_RESULT_COUNT: "3"

      HF_HUB_OFFLINE: "1"
      HF_HUB_DISABLE_TELEMETRY: "1"
      HF_HUB_DISABLE_UPDATE_CHECK: "1"
      WHISPER_MODEL: "/app/backend/data/cache/whisper/models/faster-whisper-large-v3"
      WHISPER_MODEL_DIR: "/app/backend/data/cache/whisper/models"
      WHISPER_COMPUTE_TYPE: "int8"
      WHISPER_MULTILINGUAL: "True"
      WHISPER_LANGUAGE: ""
      WHISPER_MODEL_AUTO_UPDATE: "False"
      WHISPER_VAD_FILTER: "True"
      AUDIO_STT_ALLOWED_EXTENSIONS: "mp3,wav,m4a,webm,ogg,flac,mp4,mpga,mpeg"
      AUDIO_STT_SUPPORTED_CONTENT_TYPES: "audio/*,video/webm,video/mp4"

      OFFLINE_MODE: "True"
      ENABLE_VERSION_UPDATE_CHECK: "False"
      ENABLE_IMAGE_GENERATION: "False"
    secrets:
      - webui_secret_key
    volumes:
      - openwebui-data:/app/backend/data
    ports:
      - "127.0.0.1:${WEBUI_PORT:-3000}:8080"

volumes:
  pgdata:
    name: ai-station_pgdata
  redisdata:
    name: ai-station_redisdata
  openwebui-data:
    name: ai-station-openwebui-data

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
  webui_secret_key:
    file: ./secrets/webui_secret_key.txt
YAML

# Substitute password into compose file for DATABASE_URL. Docker secrets cannot be interpolated into env at runtime.
python3 - <<PY
from pathlib import Path
p = Path("compose.yml")
text = p.read_text()
text = text.replace("\${POSTGRES_PASSWORD}", "${POSTGRES_PASSWORD}")
p.write_text(text)
PY

echo
echo "=== Canonical compose wrapper ==="
cat > scripts/compose-ai-station.sh <<'BASH2'
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

exec docker compose \
  --project-name ai-station \
  --env-file .env \
  -f compose.yml \
  "$@"
BASH2
chmod +x scripts/compose-ai-station.sh

echo
echo "=== Canonical lifecycle scripts ==="
cat > scripts/start.sh <<'BASH2'
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
BASH2

cat > scripts/stop.sh <<'BASH2'
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

./scripts/compose-ai-station.sh stop open-webui llm-general embedder searxng tika redis postgres || true
systemctl stop ai-station-ui-gateway 2>/dev/null || true
systemctl stop ai-station-gateway 2>/dev/null || true
echo "AI Station stopped."
BASH2

cat > scripts/status.sh <<'BASH2'
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

echo "=== Containers ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true

echo
echo "=== Systemd ==="
systemctl is-active docker || true
systemctl is-active ai-station-gateway || true
systemctl is-active ai-station-ui-gateway || true

echo
echo "=== Endpoints ==="
curl -I --max-time 10 http://127.0.0.1:3000 || true
curl -s --max-time 10 http://127.0.0.1:8890/v1/models | jq '.data[].id' || true
curl -s --max-time 10 http://127.0.0.1:9998/tika || true
curl -s --max-time 10 "http://127.0.0.1:8889/search?q=test&format=json" | jq '.results | length' || true

echo
echo "=== Disk ==="
df -h /
du -sh /srv/ai-station/models 2>/dev/null || true
docker system df || true
BASH2

cat > scripts/logs.sh <<'BASH2'
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-open-webui}"

case "$TARGET" in
  open-webui) docker logs -f ai-station-open-webui-1 ;;
  tika) docker logs -f ai-station-tika ;;
  searxng) docker logs -f ai-station-searxng ;;
  general) ./scripts/compose-ai-station.sh logs -f llm-general ;;
  embedder) ./scripts/compose-ai-station.sh logs -f embedder ;;
  gateway) journalctl -u ai-station-gateway -f --no-pager ;;
  ui-gateway) journalctl -u ai-station-ui-gateway -f --no-pager ;;
  *) echo "Usage: $0 {open-webui|tika|searxng|general|embedder|gateway|ui-gateway}"; exit 2 ;;
esac
BASH2

cat > scripts/verify.sh <<'BASH2'
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
BASH2

chmod +x scripts/start.sh scripts/stop.sh scripts/status.sh scripts/logs.sh scripts/verify.sh

echo
echo "=== Fix UI Gateway systemd unit ==="
cat > /etc/systemd/system/ai-station-ui-gateway.service <<'UNIT'
[Unit]
Description=AI Station UI Gateway
After=network-online.target docker.service ai-station-gateway.service
Wants=network-online.target docker.service

[Service]
Type=simple
WorkingDirectory=/opt/ai-station
Environment=AI_STATION_UI_GATEWAY_HOST=0.0.0.0
Environment=AI_STATION_UI_GATEWAY_PORT=8890
Environment=AI_STATION_GATEWAY_UPSTREAM=http://127.0.0.1:8888/v1
Environment=AI_STATION_TIKA_URL=http://127.0.0.1:9998
Environment=AI_STATION_OPENWEBUI_URL=http://127.0.0.1:3000
ExecStart=/usr/bin/python3 /opt/ai-station/apps/ui-gateway/ui_gateway.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable ai-station-gateway ai-station-ui-gateway

echo
echo "=== Write .gitignore ==="
cat > .gitignore <<'EOF'
.env
.env.*
!.env.example

secrets/
_archive/
support/
backups/

__pycache__/
*.pyc
*.pyo
*.log
*.tmp
*.bak*
*.old*
*.backup*

.vscode/
.idea/

*.gguf
*.safetensors
*.bin
*.onnx
*.pt
*.pth
*.tar
*.tar.gz
*.zip
EOF

echo
echo "=== Move obsolete files out of default path ==="
mkdir -p "$ARCHIVE/obsolete-default-path"

for f in \
  compose.ocr.yml \
  compose.context.override.yml \
  compose.console.yml \
  compose.healthcheck.yml \
  compose.models.yml \
  compose.openwebui.override.yml \
  compose.search.yml \
  compose.tika.yml
do
  [ -f "$f" ] && mv "$f" "$ARCHIVE/obsolete-default-path/" || true
done

for f in \
  scripts/ai-station-hard-reset-upload-stack.sh \
  scripts/ai-station-fix-stt-large-v3-runtime.sh \
  scripts/ai-station-repair-runtime.sh \
  scripts/ai-station-user-start.sh \
  scripts/ai-station-user-stop.sh \
  scripts/ai-station-ingest-file.sh \
  scripts/ai-station-admin-action.sh \
  scripts/ai-station-manager-action.sh
do
  [ -f "$f" ] && mv "$f" "$ARCHIVE/obsolete-default-path/" || true
done

echo
echo "=== Start clean runtime ==="
./scripts/start.sh

echo
echo "=== Verify clean runtime ==="
./scripts/verify.sh

echo
echo "=== Done ==="
echo "Old files archived in: $ARCHIVE"
