#!/usr/bin/env bash
# Windows "AI Station.cmd" entrypoint — start the full local platform.
set -Eeuo pipefail

ROOT="/opt/ai-station"
cd "$ROOT"

if [[ ! -x "$ROOT/scripts/ai" ]]; then
  echo "ERROR: missing $ROOT/scripts/ai"
  exit 1
fi

# Prefer last active heavy profile; default to general.
PROFILE="general"
STATE_FILE="/srv/ai-station/runtime/active-heavy-profile"
if [[ -f "$STATE_FILE" ]]; then
  CANDIDATE="$(tr -d '[:space:]' <"$STATE_FILE" || true)"
  case "$CANDIDATE" in
    general|coder|reasoning|vision) PROFILE="$CANDIDATE" ;;
  esac
fi

exec "$ROOT/scripts/ai" start --profile "$PROFILE"
