#!/usr/bin/env bash
# Quarantine unreferenced model directories under /srv/ai-station/quarantine.
# Reversible: move the directory back to models/ to restore.
set -Eeuo pipefail

DATA_ROOT="${AI_STATION_DATA:-/srv/ai-station}"
MODELS_DIR="${MODELS_DIR:-$DATA_ROOT/models}"
QUARANTINE_DIR="${QUARANTINE_DIR:-$DATA_ROOT/quarantine}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
TARGET="${1:-coder/qwen3-coder-next}"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  TARGET="${2:-coder/qwen3-coder-next}"
fi

SRC="$MODELS_DIR/$TARGET"
DEST="$QUARANTINE_DIR/${STAMP}-$(basename "$TARGET")"

if [[ ! -e "$SRC" ]]; then
  echo "Nothing to quarantine: $SRC"
  exit 0
fi

echo "Source:      $SRC"
echo "Destination: $DEST"
echo "Rollback:    mv '$DEST' '$SRC'"

if (( DRY_RUN )); then
  echo "Dry-run only; no changes made."
  exit 0
fi

mkdir -p "$QUARANTINE_DIR"
mv "$SRC" "$DEST"
printf '%s\n' "quarantined_at=$STAMP" "source=$SRC" "destination=$DEST" \
  >"$DEST/QUARANTINE.txt" 2>/dev/null \
  || printf '%s\n' "quarantined_at=$STAMP" "source=$SRC" "destination=$DEST" \
  >"${DEST}.QUARANTINE.txt"

echo "Quarantined $TARGET -> $DEST"
