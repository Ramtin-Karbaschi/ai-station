#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_ROOT="${AI_STATION_DATA:-/srv/ai-station}"
BACKUPS_ROOT="$DATA_ROOT/backups"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUPS_ROOT/$TS"

mkdir -p "$BACKUPS_ROOT"
WORK_DIR="$(mktemp -d "$BACKUPS_ROOT/.partial-${TS}-XXXXXX")"
cleanup() {
  rm -rf -- "$WORK_DIR"
}
trap cleanup EXIT

cd "$ROOT"
SNAPSHOT_STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$ROOT/scripts/compose-ai-station.sh" exec -T postgres sh -lc \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "$WORK_DIR/ai_station_postgres.dump"

tar -C "$DATA_ROOT/data" -czf "$WORK_DIR/ai_station_files.tar.gz" uploads artifacts

cp compose.yml "$WORK_DIR/compose.yml"
cp .env.example "$WORK_DIR/env.example"

# The volume is optional for backward compatibility with installations that
# predate Open WebUI persistence. When present, capture it without touching
# the running service; failures are fatal once Docker confirms the volume.
OPENWEBUI_VOLUME="${AI_STATION_OPENWEBUI_VOLUME:-ai-station-openwebui-data}"
if [[ "${AI_STATION_OPENWEBUI_VOLUME_BACKUP:-0}" == "1" ]]; then
  command -v docker >/dev/null 2>&1 || {
    echo "ERROR: Docker is required for the requested Open WebUI volume backup" >&2
    exit 1
  }
  docker volume inspect "$OPENWEBUI_VOLUME" >/dev/null 2>&1 || {
    echo "ERROR: requested Open WebUI volume not found: $OPENWEBUI_VOLUME" >&2
    exit 1
  }
  "$ROOT/scripts/backup-openwebui-volume.sh" "$OPENWEBUI_VOLUME" \
    "$WORK_DIR/ai_station_openwebui_data.tar.gz" \
    "$WORK_DIR/openwebui_volume_manifest.json"

  # Open WebUI and LiteLLM use separate PostgreSQL databases in the same
  # container.  Full-recovery mode captures both; failure is fatal so a
  # successful-looking backup cannot silently omit gateway state.
  LITELLM_DB="${AI_STATION_LITELLM_DB:-litellm}"
  if [[ ! "$LITELLM_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "ERROR: invalid LiteLLM database identifier" >&2
    exit 1
  fi
  "$ROOT/scripts/compose-ai-station.sh" exec -T postgres sh -lc \
    'exec pg_dump -U "$POSTGRES_USER" -d "$1" -Fc' sh "$LITELLM_DB" \
    > "$WORK_DIR/ai_station_litellm.dump"
  SNAPSHOT_FINISHED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$WORK_DIR/database_backup_manifest.json" "$LITELLM_DB" \
    "$SNAPSHOT_STARTED_UTC" "$SNAPSHOT_FINISHED_UTC" <<'PY'
import json
import sys
from pathlib import Path

output, database, started, finished = sys.argv[1:]
Path(output).write_text(json.dumps({
    "schema": 1,
    "mode": "complete",
    "database": database,
    "snapshot_started_utc": started,
    "snapshot_finished_utc": finished,
    "artifacts": ["ai_station_postgres.dump", "ai_station_litellm.dump"],
}, sort_keys=True) + "\n", encoding="utf-8")
PY
else
  echo "WARNING: Open WebUI volume backup skipped; set AI_STATION_OPENWEBUI_VOLUME_BACKUP=1 for RB-04" >&2
fi
(
  cd "$WORK_DIR"
  find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%f\n' | sort | xargs sha256sum > SHA256SUMS
)

# Keep a same-second backup from overwriting or nesting inside the published one.
mv -nT -- "$WORK_DIR" "$BACKUP_DIR"
if [[ -d "$WORK_DIR" ]]; then
  echo "ERROR: backup already exists for $TS; retry with a new timestamp." >&2
  exit 1
fi
chmod 0700 "$BACKUP_DIR"
trap - EXIT
echo "Backup created: $BACKUP_DIR"
