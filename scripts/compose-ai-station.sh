#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

exec docker compose \
  --project-name ai-station \
  --env-file .env \
  -f compose.yml \
  "$@"
