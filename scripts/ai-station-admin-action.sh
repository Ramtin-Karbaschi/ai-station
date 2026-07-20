#!/usr/bin/env bash
# Compatibility shim — Admin menu now uses the unified manager action script.
set -Eeuo pipefail
exec /opt/ai-station/scripts/ai-station-manager-action.sh "$@"
