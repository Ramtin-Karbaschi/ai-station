#!/usr/bin/env bash
# Compatibility shim — Windows Manager / old Desktop shortcuts.
# Canonical day-to-day entrypoint is scripts/ai.
set -Eeuo pipefail
ROOT="/opt/ai-station"
exec "$ROOT/scripts/ai" "$@"
