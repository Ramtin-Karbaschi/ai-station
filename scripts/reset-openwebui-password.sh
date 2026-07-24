#!/usr/bin/env bash
# Reset Open WebUI local admin password (PostgreSQL auth table).
# Usage:
#   ./scripts/reset-openwebui-password.sh [email] [new-password]
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

EMAIL="${1:-}"
NEW_PASSWORD="${2:-}"

if ! curl -fsS --max-time 5 http://127.0.0.1:3000/api/config >/dev/null; then
  echo "ERROR: Open WebUI is not reachable on http://127.0.0.1:3000"
  echo "Start the platform first: ai start --profile general"
  exit 1
fi

if [[ -z "$EMAIL" ]]; then
  EMAIL="$(
    ./scripts/compose-ai-station.sh exec -T postgres \
      psql -U openwebui -d openwebui -Atc "SELECT email FROM auth ORDER BY email LIMIT 1;"
  )"
fi

if [[ -z "$EMAIL" ]]; then
  echo "ERROR: no Open WebUI user found in auth table."
  exit 1
fi

if [[ -z "$NEW_PASSWORD" ]]; then
  NEW_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)"
fi

# Hash inside Open WebUI (same bcrypt implementation it uses for verify).
HASH="$(
  ./scripts/compose-ai-station.sh exec -T \
    -e OWUI_RESET_PASSWORD="$NEW_PASSWORD" \
    open-webui python - <<'PY'
import bcrypt, os
password = os.environ["OWUI_RESET_PASSWORD"].encode("utf-8")
print(bcrypt.hashpw(password, bcrypt.gensalt(rounds=12)).decode("utf-8"))
PY
)"

if [[ -z "$HASH" || "$HASH" != \$2* ]]; then
  echo "ERROR: failed to generate bcrypt hash."
  exit 1
fi

# Update via psycopg in a one-shot python on the host using local TCP to published postgres.
# Prefer in-container psql with a temp SQL file to avoid shell $ expansion on bcrypt hash.
TMP_SQL="$(mktemp)"
EMAIL="$EMAIL" HASH="$HASH" TMP_SQL="$TMP_SQL" python3 - <<'PY'
from pathlib import Path
import os
email = os.environ["EMAIL"]
hashed = os.environ["HASH"]
path = Path(os.environ["TMP_SQL"])
# PostgreSQL dollar-quoting avoids escaping bcrypt '$' characters.
path.write_text(
    f"UPDATE auth SET password = $bcrypt${hashed}$bcrypt$ WHERE email = $mail${email}$mail$;\n",
    encoding="utf-8",
)
print("sql_ready")
PY

./scripts/compose-ai-station.sh exec -T postgres \
  psql -U openwebui -d openwebui -v ON_ERROR_STOP=1 <"$TMP_SQL"
rm -f "$TMP_SQL"

HTTP_CODE="$(
  EMAIL="$EMAIL" NEW_PASSWORD="$NEW_PASSWORD" python3 - <<'PY'
import json, os, urllib.error, urllib.request
payload = json.dumps({
    "email": os.environ["EMAIL"],
    "password": os.environ["NEW_PASSWORD"],
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:3000/api/v1/auths/signin",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=20) as resp:
        open("/tmp/ai-station-signin.json", "wb").write(resp.read())
        print(resp.status)
except urllib.error.HTTPError as e:
    open("/tmp/ai-station-signin.json", "wb").write(e.read())
    print(e.code)
except Exception as e:
    open("/tmp/ai-station-signin.json", "w", encoding="utf-8").write(repr(e))
    print("000")
PY
)"

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "ERROR: password updated in DB but sign-in probe failed (HTTP ${HTTP_CODE})."
  echo "Response:"
  cat /tmp/ai-station-signin.json 2>/dev/null || true
  exit 1
fi

cat <<EOF

Open WebUI password reset successful.

  Email:    ${EMAIL}
  Password: ${NEW_PASSWORD}
  UI:       http://127.0.0.1:3000

Sign-in probe: HTTP ${HTTP_CODE}

Store this password securely. It will not be shown again by this script.
EOF
