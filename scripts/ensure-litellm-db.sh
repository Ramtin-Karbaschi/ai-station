#!/usr/bin/env bash
# Ensure the LiteLLM database exists on an already-initialized Postgres volume.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE=("$ROOT/scripts/compose-ai-station.sh")

POSTGRES_USER="$(
  python3 - <<'PY'
from pathlib import Path
user = "openwebui"
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == "POSTGRES_USER":
        user = value.strip().strip('"').strip("'")
        break
print(user)
PY
)"

if ! "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx postgres; then
  echo "ERROR: postgres service is not running."
  exit 1
fi

# Prefer the local superuser over the app role (app role may lack CREATEDB).
SUPERUSER="ai_station"
if ! "${COMPOSE[@]}" exec -T postgres psql -U "$SUPERUSER" -d postgres -c 'SELECT 1' >/dev/null 2>&1; then
  SUPERUSER="$POSTGRES_USER"
fi

"${COMPOSE[@]}" exec -T postgres \
  psql -U "$SUPERUSER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT 'CREATE DATABASE litellm OWNER ${POSTGRES_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')\gexec
GRANT ALL PRIVILEGES ON DATABASE litellm TO ${POSTGRES_USER};
SQL

echo "OK: litellm database ready."
