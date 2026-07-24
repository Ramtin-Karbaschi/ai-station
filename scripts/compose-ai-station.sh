#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # Read COMPOSE_FILE without sourcing the whole .env (values may contain spaces).
  COMPOSE_FILE="$(
    python3 - <<'PY'
from pathlib import Path
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == "COMPOSE_FILE":
        print(value.strip().strip('"').strip("'"))
        break
PY
  )"
  if [[ -n "${COMPOSE_FILE}" ]]; then
    export COMPOSE_FILE
  fi

  PROJECT_NAME="$(
    python3 - <<'PY'
from pathlib import Path
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == "COMPOSE_PROJECT_NAME":
        print(value.strip().strip('"').strip("'"))
        break
PY
  )"
  if [[ -n "${PROJECT_NAME}" ]]; then
    export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
  fi
fi

exec docker compose \
  --project-name "${COMPOSE_PROJECT_NAME:-ai-station}" \
  --env-file .env \
  "$@"
