#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="/opt/ai-station"
exec "$ROOT/scripts/ai" models stop
