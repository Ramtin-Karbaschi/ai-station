#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

TS="$(date +%Y%m%d-%H%M%S)"
REPORT="/opt/ai-station/support/fix-postgres-password-${TS}"
mkdir -p "$REPORT"

echo "=== Fix PostgreSQL password mismatch for Open WebUI ==="
echo "Report: $REPORT"

if [ ! -f .env ]; then
  echo "ERROR: .env not found."
  exit 1
fi

POSTGRES_PASSWORD="$(grep -E '^POSTGRES_PASSWORD=' .env | tail -1 | cut -d= -f2- | sed 's/^"//;s/"$//')"

if [ -z "$POSTGRES_PASSWORD" ]; then
  echo "ERROR: POSTGRES_PASSWORD is missing in .env"
  exit 1
fi

mkdir -p secrets
printf '%s\n' "$POSTGRES_PASSWORD" > secrets/postgres_password.txt
chmod 600 secrets/postgres_password.txt

echo
echo "=== Stop restarting Open WebUI ==="
docker rm -f ai-station-open-webui-1 >/dev/null 2>&1 || true

echo
echo "=== Ensure PostgreSQL is running ==="
systemctl start docker

./scripts/compose-ai-station.sh up -d postgres

for i in $(seq 1 90); do
  if docker ps --format '{{.Names}}' | grep -qx 'ai-station-postgres-1'; then
    if docker exec ai-station-postgres-1 pg_isready >/dev/null 2>&1; then
      echo "PostgreSQL is ready."
      break
    fi
  fi

  sleep 2

  if [ "$i" = "90" ]; then
    echo "ERROR: PostgreSQL did not become ready."
    docker logs --tail=300 ai-station-postgres-1 || true
    exit 1
  fi
done

echo
echo "=== Inspect PostgreSQL roles ==="

# Local unix-socket access inside the official Postgres container commonly allows catalog inspection
# even when TCP password auth is failing. We use this only to find the real superuser.
ROLE_REPORT="$REPORT/roles.txt"

for candidate in postgres ai_station openwebui; do
  echo "--- candidate: $candidate ---" | tee -a "$ROLE_REPORT"

  docker exec -i ai-station-postgres-1 sh -lc \
    "psql -U '$candidate' -d postgres -tAc \"SELECT rolname, rolsuper, rolcreaterole FROM pg_roles ORDER BY rolname;\"" \
    2>&1 | tee -a "$ROLE_REPORT" || true
done

SUPERUSER="$(
  for candidate in postgres ai_station openwebui; do
    if docker exec -i ai-station-postgres-1 sh -lc \
      "psql -U '$candidate' -d postgres -tAc \"SELECT rolname FROM pg_roles WHERE rolname=current_user AND rolsuper IS TRUE;\"" \
      2>/dev/null | grep -E '^(postgres|ai_station|openwebui)$' >/tmp/ai-station-superuser-candidate 2>/dev/null; then
        cat /tmp/ai-station-superuser-candidate
        exit 0
    fi
  done
)"

if [ -z "${SUPERUSER:-}" ]; then
  echo "ERROR: Could not find a PostgreSQL superuser reachable inside the container."
  echo "Role report:"
  cat "$ROLE_REPORT"
  exit 1
fi

echo "Detected PostgreSQL superuser: $SUPERUSER"

echo
echo "=== Reset openwebui role/database using real superuser ==="

docker exec -i ai-station-postgres-1 sh -lc "psql -U '$SUPERUSER' -d postgres -v app_password=\"$POSTGRES_PASSWORD\"" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'openwebui') THEN
    CREATE ROLE openwebui LOGIN;
  END IF;
END $$;

ALTER ROLE openwebui WITH LOGIN PASSWORD :'app_password';
SQL

if ! docker exec -i ai-station-postgres-1 sh -lc \
  "psql -U '$SUPERUSER' -d postgres -tAc \"SELECT 1 FROM pg_database WHERE datname='openwebui'\"" | grep -q 1; then
  docker exec -i ai-station-postgres-1 sh -lc \
    "createdb -U '$SUPERUSER' -O openwebui openwebui"
fi

docker exec -i ai-station-postgres-1 sh -lc "psql -U '$SUPERUSER' -d openwebui" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;

ALTER DATABASE openwebui OWNER TO openwebui;
GRANT ALL PRIVILEGES ON DATABASE openwebui TO openwebui;
GRANT ALL ON SCHEMA public TO openwebui;
ALTER SCHEMA public OWNER TO openwebui;

ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO openwebui;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO openwebui;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO openwebui;
SQL

echo
echo "=== Verify TCP password auth exactly like Open WebUI will use it ==="

docker exec -e PGPASSWORD="$POSTGRES_PASSWORD" -i ai-station-postgres-1 sh -lc \
  "psql -h 127.0.0.1 -U openwebui -d openwebui -tAc 'SELECT current_user, current_database();'"

echo
echo "=== Recreate Open WebUI ==="

./scripts/compose-ai-station.sh up -d --force-recreate open-webui

echo
echo "=== Wait for Open WebUI ==="

for i in $(seq 1 180); do
  if curl -fsS --max-time 5 http://127.0.0.1:3000 >/dev/null 2>&1; then
    echo "OK: Open WebUI is ready."
    break
  fi

  STATUS="$(docker inspect -f '{{.State.Status}} {{.State.Restarting}}' ai-station-open-webui-1 2>/dev/null || true)"

  if echo "$STATUS" | grep -q "restarting true"; then
    echo "ERROR: Open WebUI is still restarting."
    docker logs --tail=250 ai-station-open-webui-1 || true
    exit 1
  fi

  sleep 2

  if [ "$i" = "180" ]; then
    echo "ERROR: Open WebUI did not become ready."
    docker logs --tail=300 ai-station-open-webui-1 || true
    exit 1
  fi
done

echo
echo "=== Verify local Whisper after Open WebUI is running ==="

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
echo "=== Done ==="
