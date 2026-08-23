#!/usr/bin/env bash
# Compatibility alias → ai models use
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-}"
if [[ -z "$MODE" ]]; then
  echo "Usage: $0 <general|coder|reasoning|vision|ornith|qwen38|longwriter>" >&2
  exit 2
fi
exec "$ROOT/scripts/ai" models use "$MODE"
