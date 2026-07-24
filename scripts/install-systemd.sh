#!/usr/bin/env bash
# Install or refresh AI Station host gateway systemd units (loopback-only).
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${UNIT_DIR:-/etc/systemd/system}"

install -m 0644 \
  "$ROOT/infra/systemd/ai-station-gateway.service" \
  "$UNIT_DIR/ai-station-gateway.service"
install -m 0644 \
  "$ROOT/infra/systemd/ai-station-ui-gateway.service" \
  "$UNIT_DIR/ai-station-ui-gateway.service"

systemctl daemon-reload
systemctl enable ai-station-gateway.service ai-station-ui-gateway.service
systemctl restart ai-station-gateway.service ai-station-ui-gateway.service

echo "Installed systemd units from infra/systemd/ (bind 127.0.0.1)."
