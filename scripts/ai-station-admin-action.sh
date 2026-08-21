#!/usr/bin/env bash
# Compatibility shim — Admin menu uses the unified CLI.
set -Eeuo pipefail
exec /opt/ai-station/scripts/ai "$@"
