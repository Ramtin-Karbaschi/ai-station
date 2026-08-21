#!/usr/bin/env bash
# Makefile / muscle-memory wrapper → unified CLI.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ $# -gt 0 && "$1" != --* ]]; then
  exec "$ROOT/scripts/ai" start --profile "$1"
fi
exec "$ROOT/scripts/ai" start "$@"
