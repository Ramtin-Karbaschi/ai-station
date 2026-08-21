#!/usr/bin/env bash
# Makefile / muscle-memory wrapper → unified CLI.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/ai" status "$@"
