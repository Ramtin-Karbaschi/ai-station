#!/usr/bin/env bash
# Compatibility alias → ai models stop
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/ai" models stop "$@"
