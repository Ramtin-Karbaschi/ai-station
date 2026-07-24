#!/usr/bin/env bash
set -euo pipefail

cd /opt/ai-station

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/srv/ai-station/backups/$TS"
mkdir -p "$BACKUP_DIR"

docker compose exec -T postgres pg_dump -U ai_station -d ai_station -Fc > "$BACKUP_DIR/ai_station_postgres.dump"

tar -C /srv/ai-station/data -czf "$BACKUP_DIR/ai_station_files.tar.gz" uploads artifacts

cp compose.yml "$BACKUP_DIR/compose.yml"
cp .env.example "$BACKUP_DIR/env.example"

sha256sum "$BACKUP_DIR"/* > "$BACKUP_DIR/SHA256SUMS"

echo "Backup created: $BACKUP_DIR"
