#!/usr/bin/env bash
# Compatibility shim — stop via the unified CLI.
set -Eeuo pipefail
ROOT="/opt/ai-station"
exec "$ROOT/scripts/ai" stop "$@"
