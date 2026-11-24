#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # Read COMPOSE_FILE without sourcing the whole .env (values may contain spaces).
  env_compose_file="$(
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
  if [[ -z "${COMPOSE_FILE:-}" && -n "${env_compose_file}" ]]; then
    export COMPOSE_FILE="$env_compose_file"
  fi

  env_project_name="$(
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
  if [[ -z "${COMPOSE_PROJECT_NAME:-}" && -n "${env_project_name}" ]]; then
    export COMPOSE_PROJECT_NAME="$env_project_name"
  fi
fi

OPERATOR_ENV="${AI_STATION_DATA:-/srv/ai-station}/runtime/compose-operator.env"
ENV_FILE_ARGS=()
if [[ -f .env ]]; then
  ENV_FILE_ARGS+=(--env-file .env)
fi
if [[ -f "$OPERATOR_ENV" ]]; then
  ENV_FILE_ARGS+=(--env-file "$OPERATOR_ENV")
fi

# Docker Desktop / WSL interop: when this script runs from the Windows control
# panel, PowerShell captures stdout into its pipeline while stderr stays on the
# console. Compose then selects its TTY progress renderer from one stream and
# asks the other one for a console, which fails with
# "failed to get console: provided file is not a console".
# Force the plain renderer unless both streams really are a terminal.
UI_ARGS=()
if [[ -n "${AI_STATION_COMPOSE_PROGRESS:-}" ]]; then
  UI_ARGS=(--ansi never --progress "${AI_STATION_COMPOSE_PROGRESS}")
elif [[ ! -t 1 || ! -t 2 ]]; then
  UI_ARGS=(--ansi never --progress plain)
fi

exec docker compose \
  --project-name "${COMPOSE_PROJECT_NAME:-ai-station}" \
  "${ENV_FILE_ARGS[@]}" \
  ${UI_ARGS[@]+"${UI_ARGS[@]}"} \
  "$@"
