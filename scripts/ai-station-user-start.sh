#!/usr/bin/env bash
# Compatibility shim — Windows Desktop quick-start.
# Profile restore lives in: ai start (last active, else general).
set -Eeuo pipefail
ROOT="/opt/ai-station"
exec "$ROOT/scripts/ai" start "$@"
