#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

TS="$(date +%Y%m%d-%H%M%S)"
REPORT="/opt/ai-station/support/fix-openwebui-${TS}"
mkdir -p "$REPORT"

echo "=== Fix Open WebUI restart loop ==="
echo "Report: $REPORT"

cp -a compose.yml "$REPORT/compose.yml.before" 2>/dev/null || true
cp -a .env "$REPORT/env.before" 2>/dev/null || true

touch .env
mkdir -p secrets

get_env() {
  local key="$1"
  grep -E "^${key}=" .env 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/^"//;s/"$//' || true
}

set_env() {
  local key="$1"
  local value="$2"

  if grep -qE "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#g" .env
  else
    echo "${key}=${value}" >> .env
  fi
}

POSTGRES_PASSWORD="$(get_env POSTGRES_PASSWORD)"
WEBUI_SECRET_KEY="$(get_env WEBUI_SECRET_KEY)"

if [ -z "${POSTGRES_PASSWORD}" ]; then
  if [ -f secrets/postgres_password.txt ]; then
    POSTGRES_PASSWORD="$(cat secrets/postgres_password.txt)"
  else
    POSTGRES_PASSWORD="$(openssl rand -hex 24)"
    echo "$POSTGRES_PASSWORD" > secrets/postgres_password.txt
  fi
fi

if [ -z "${WEBUI_SECRET_KEY}" ]; then
  if [ -f secrets/webui_secret_key.txt ]; then
    WEBUI_SECRET_KEY="$(cat secrets/webui_secret_key.txt)"
  elif [ -f secrets/app_secret_key.txt ]; then
    WEBUI_SECRET_KEY="$(cat secrets/app_secret_key.txt)"
  else
    WEBUI_SECRET_KEY="$(openssl rand -hex 32)"
    echo "$WEBUI_SECRET_KEY" > secrets/webui_secret_key.txt
  fi
fi

chmod 600 secrets/*.txt 2>/dev/null || true

set_env COMPOSE_PROJECT_NAME "ai-station"
set_env POSTGRES_DB "openwebui"
set_env POSTGRES_USER "openwebui"
set_env POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
set_env WEBUI_SECRET_KEY "$WEBUI_SECRET_KEY"
set_env MODELS_DIR "/srv/ai-station/models"
set_env GENERAL_MODEL_FILE "general/qwen3.6-35b-a3b-ud-q4_k_m.gguf"
set_env EMBEDDING_MODEL_FILE "embedding/qwen3-embedding-0.6b-q8_0.gguf"
set_env GENERAL_CONTEXT "8192"
set_env EMBEDDING_CONTEXT "8192"
set_env WEBUI_PORT "3000"

echo
echo "=== Patch compose.yml ==="

python3 - <<'PY'
from pathlib import Path
import re

p = Path("compose.yml")
text = p.read_text()

def set_env_line(text: str, key: str, value: str) -> str:
    pattern = rf'^(\s*){re.escape(key)}:.*$'
    if re.search(pattern, text, flags=re.MULTILINE):
        return re.sub(pattern, rf'\1{key}: {value}', text, flags=re.MULTILINE)

    marker = "    environment:\n"
    if marker not in text:
        raise SystemExit("environment block not found")

    return text.replace(marker, marker + f"      {key}: {value}\n", 1)

# PostgreSQL: use .env value directly. This is simpler and more portable for this repo.
text = re.sub(
    r'^(\s*)POSTGRES_PASSWORD_FILE:\s*/run/secrets/postgres_password\s*$',
    r'\1POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"',
    text,
    flags=re.MULTILINE,
)

# Open WebUI: use the officially supported env var.
text = re.sub(
    r'^(\s*)WEBUI_SECRET_KEY_FILE:\s*/run/secrets/webui_secret_key\s*$',
    r'\1WEBUI_SECRET_KEY: "${WEBUI_SECRET_KEY}"',
    text,
    flags=re.MULTILINE,
)

if "WEBUI_SECRET_KEY:" not in text:
    text = set_env_line(text, "WEBUI_SECRET_KEY", '"${WEBUI_SECRET_KEY}"')

# Normalize database URLs.
text = re.sub(
    r'^(\s*)DATABASE_URL:.*$',
    r'\1DATABASE_URL: "postgresql://${POSTGRES_USER:-openwebui}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-openwebui}"',
    text,
    flags=re.MULTILINE,
)

text = re.sub(
    r'^(\s*)PGVECTOR_DB_URL:.*$',
    r'\1PGVECTOR_DB_URL: "postgresql://${POSTGRES_USER:-openwebui}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-openwebui}"',
    text,
    flags=re.MULTILINE,
)

# Single worker is the safe default for this local stack.
text = set_env_line(text, "UVICORN_WORKERS", '"1"')

# Hard lock extraction and STT.
text = set_env_line(text, "CONTENT_EXTRACTION_ENGINE", '"tika"')
text = set_env_line(text, "TIKA_SERVER_URL", '"http://tika:9998"')
text = set_env_line(text, "HF_HUB_OFFLINE", '"1"')
text = set_env_line(text, "WHISPER_MODEL", '"/app/backend/data/cache/whisper/models/faster-whisper-large-v3"')
text = set_env_line(text, "WHISPER_MODEL_DIR", '"/app/backend/data/cache/whisper/models"')
text = set_env_line(text, "WHISPER_COMPUTE_TYPE", '"int8"')

p.write_text(text)
print("compose.yml patched.")
PY

echo
echo "=== Patch UI Gateway systemd unit ==="

cat > /etc/systemd/system/ai-station-ui-gateway.service <<'UNIT'
[Unit]
Description=AI Station UI Gateway
After=network-online.target docker.service ai-station-gateway.service
Wants=network-online.target docker.service

[Service]
Type=simple
WorkingDirectory=/opt/ai-station
Environment=AI_STATION_UI_GATEWAY_HOST=127.0.0.1
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
systemctl restart ai-station-gateway || true
systemctl restart ai-station-ui-gateway || true

echo
echo "=== Start core dependencies ==="

systemctl start docker

./scripts/compose-ai-station.sh up -d postgres redis searxng tika embedder llm-general

echo
echo "=== Wait for PostgreSQL container ==="

for i in $(seq 1 90); do
  if docker ps --format '{{.Names}}' | grep -qx 'ai-station-postgres-1'; then
    if docker exec ai-station-postgres-1 pg_isready >/dev/null 2>&1; then
      echo "PostgreSQL process is ready."
      break
    fi
  fi
  sleep 2

  if [ "$i" = "90" ]; then
    echo "ERROR: PostgreSQL did not become ready."
    docker logs --tail=200 ai-station-postgres-1 || true
    exit 1
  fi
done

echo
echo "=== Normalize PostgreSQL role/database without deleting existing volume ==="

ADMIN_USER=""

for candidate in openwebui ai_station postgres; do
  if docker exec -i ai-station-postgres-1 sh -lc "psql -U '${candidate}' -d postgres -tAc 'SELECT 1'" >/dev/null 2>&1; then
    ADMIN_USER="$candidate"
    break
  fi
done

if [ -z "$ADMIN_USER" ]; then
  echo "ERROR: Could not find a local PostgreSQL admin user."
  docker logs --tail=200 ai-station-postgres-1 || true
  exit 1
fi

echo "PostgreSQL admin user detected: ${ADMIN_USER}"

docker exec -i ai-station-postgres-1 sh -lc "psql -U '${ADMIN_USER}' -d postgres" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'openwebui') THEN
    CREATE ROLE openwebui LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  ELSE
    ALTER ROLE openwebui WITH LOGIN PASSWORD '${POSTGRES_PASSWORD}';
  END IF;
END
\$\$;
SQL

if ! docker exec -i ai-station-postgres-1 sh -lc "psql -U '${ADMIN_USER}' -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='openwebui'\"" | grep -q 1; then
  docker exec -i ai-station-postgres-1 sh -lc "createdb -U '${ADMIN_USER}' -O openwebui openwebui"
fi

docker exec -i ai-station-postgres-1 sh -lc "psql -U '${ADMIN_USER}' -d openwebui" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;
SQL

echo
echo "=== Recreate Open WebUI ==="

docker rm -f ai-station-open-webui-1 >/dev/null 2>&1 || true

./scripts/compose-ai-station.sh up -d --force-recreate open-webui

echo
echo "=== Wait for Open WebUI ==="

for i in $(seq 1 180); do
  STATUS="$(docker inspect -f '{{.State.Status}} {{.State.Restarting}}' ai-station-open-webui-1 2>/dev/null || true)"

  if curl -fsS --max-time 5 http://127.0.0.1:3000 >/dev/null 2>&1; then
    echo "OK: Open WebUI is ready."
    break
  fi

  if echo "$STATUS" | grep -q "restarting true"; then
    echo "Open WebUI is restarting. Showing logs:"
    docker logs --tail=250 ai-station-open-webui-1 || true
    exit 1
  fi

  sleep 2

  if [ "$i" = "180" ]; then
    echo "ERROR: Open WebUI did not become ready."
    docker inspect ai-station-open-webui-1 > "$REPORT/openwebui-inspect.json" 2>&1 || true
    docker logs --tail=300 ai-station-open-webui-1 > "$REPORT/openwebui-logs.txt" 2>&1 || true
    cat "$REPORT/openwebui-logs.txt"
    exit 1
  fi
done

echo
echo "=== Verify Whisper inside running Open WebUI ==="

docker exec -e HF_HUB_OFFLINE=1 -i ai-station-open-webui-1 python - <<'PY'
from faster_whisper import WhisperModel

WhisperModel(
    "/app/backend/data/cache/whisper/models/faster-whisper-large-v3",
    device="cpu",
    compute_type="int8",
    local_files_only=True,
)

print("OK: local faster-whisper-large-v3 loaded offline.")
PY

echo
echo "=== Runtime check ==="

docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

echo
curl -I --max-time 15 http://127.0.0.1:3000 || true
curl -s --max-time 15 http://127.0.0.1:8890/v1/models | jq '.data[].id' || true
curl -s --max-time 15 http://127.0.0.1:9998/tika || true

echo
echo "=== Done ==="
echo "Report: $REPORT"
