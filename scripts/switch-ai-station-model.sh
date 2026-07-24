#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-}"

case "$MODE" in
  general|coder|reasoning|vision)
    exec "$ROOT/scripts/ai" models use "$MODE"
    ;;
  *)
    echo "Usage: $0 <general|coder|reasoning|vision>"
    exit 2
    ;;
esac
