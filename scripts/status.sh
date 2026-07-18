#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

echo "=== Containers ==="
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true

echo
echo "=== Systemd ==="
systemctl is-active docker || true
systemctl is-active ai-station-gateway || true
systemctl is-active ai-station-ui-gateway || true

echo
echo "=== Endpoints ==="
curl -I --max-time 10 http://127.0.0.1:3000 || true
curl -s --max-time 10 http://127.0.0.1:8890/v1/models | jq '.data[].id' || true
curl -s --max-time 10 http://127.0.0.1:9998/tika || true
curl -s --max-time 10 "http://127.0.0.1:8889/search?q=test&format=json" | jq '.results | length' || true

echo
echo "=== Disk ==="
df -h /
du -sh /srv/ai-station/models 2>/dev/null || true
docker system df || true
