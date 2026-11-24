#!/usr/bin/env bash
# Install the Tool Gateway without root access using the WSL user manager.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
ASSET_DIR="${AI_STATION_TOOL_ASSET_ROOT:-/srv/ai-station/data/grounding/assets}"

install -d -m 0755 "$UNIT_DIR" "$ASSET_DIR"
install -m 0644 \
  "$ROOT/infra/systemd/user/ai-station-tool-gateway.service" \
  "$UNIT_DIR/ai-station-tool-gateway.service"

systemctl --user daemon-reload
systemctl --user enable --now ai-station-tool-gateway.service

for _attempt in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8892/healthz >/dev/null 2>&1; then
    echo "Installed user Tool Gateway on http://127.0.0.1:8892."
    exit 0
  fi
  sleep 1
done

echo "ERROR: user Tool Gateway did not become healthy" >&2
systemctl --user --no-pager --full status ai-station-tool-gateway.service >&2 || true
exit 1
