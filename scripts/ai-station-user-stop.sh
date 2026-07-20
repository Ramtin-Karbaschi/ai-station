#!/usr/bin/env bash
# Windows "AI Station.cmd" entrypoint — stop the full local platform.
set -Eeuo pipefail

ROOT="/opt/ai-station"
cd "$ROOT"

if [[ ! -x "$ROOT/scripts/ai" ]]; then
  echo "ERROR: missing $ROOT/scripts/ai"
  exit 1
fi

exec "$ROOT/scripts/ai" stop
