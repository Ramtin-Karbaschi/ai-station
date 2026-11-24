#!/bin/sh
set -eu

if [ -z "${SEARXNG_SECRET:-}" ]; then
  echo "ERROR: SearXNG secret is missing; run 'ai searxng secret provision'." >&2
  exit 1
fi

exec /usr/local/searxng/entrypoint.sh "$@"
