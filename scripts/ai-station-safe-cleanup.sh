#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT_DIR="/opt/ai-station/support/cleanup-${STAMP}"
mkdir -p "$REPORT_DIR"

echo "=== AI Station Safe Cleanup ==="
echo "Report: $REPORT_DIR"
date -Iseconds | tee "$REPORT_DIR/timestamp.txt"

echo
echo "=== Before cleanup: disk ==="
df -hT | tee "$REPORT_DIR/df-before.txt"

echo
echo "=== Before cleanup: docker system df ==="
docker system df -v > "$REPORT_DIR/docker-system-df-before.txt" 2>&1 || true
cat "$REPORT_DIR/docker-system-df-before.txt"

echo
echo "=== Before cleanup: major directories ==="
{
  du -sh /opt/ai-station 2>/dev/null || true
  du -sh /srv/ai-station 2>/dev/null || true
  du -sh /srv/ai-station/models 2>/dev/null || true
  du -sh /srv/ai-station/data 2>/dev/null || true
  du -sh /var/lib/docker 2>/dev/null || true
  du -sh /root/.cache 2>/dev/null || true
} | tee "$REPORT_DIR/du-before.txt"

echo
echo "=== Cleaning apt cache ==="
apt-get autoremove -y || true
apt-get clean || true
rm -rf /var/lib/apt/lists/* || true

echo
echo "=== Cleaning Python/pip caches ==="
python3 -m pip cache purge >/dev/null 2>&1 || true
rm -rf /root/.cache/pip || true

echo
echo "=== Cleaning common temporary files older than 24h ==="
find /tmp /var/tmp -xdev -mindepth 1 -mtime +1 -print -exec rm -rf {} + 2>/dev/null || true

echo
echo "=== Cleaning project Python cache files ==="
find /opt/ai-station \
  \( -type d -name "__pycache__" \
     -o -type d -name ".pytest_cache" \
     -o -type d -name ".mypy_cache" \
     -o -type d -name ".ruff_cache" \
     -o -type d -name ".ipynb_checkpoints" \) \
  -print -exec rm -rf {} + 2>/dev/null || true

echo
echo "=== Cleaning interrupted Hugging Face partial downloads ==="
# فقط partial/incomplete؛ مدل‌های کامل را حذف نمی‌کند.
for d in \
  /root/.cache/huggingface \
  /srv/ai-station \
  /opt/ai-station
do
  if [ -d "$d" ]; then
    find "$d" -type f \( -name "*.incomplete" -o -name "*.partial" -o -name "*.part" \) -mmin +60 -print -delete 2>/dev/null || true
  fi
done

echo
echo "=== Cleaning Open WebUI incomplete HF cache files ==="
if docker ps --format '{{.Names}}' | grep -qx 'ai-station-open-webui-1'; then
  docker exec -i ai-station-open-webui-1 sh -lc '
    find /app/backend/data/cache -type f \( -name "*.incomplete" -o -name "*.partial" -o -name "*.part" \) -mmin +60 -print -delete 2>/dev/null || true
  ' || true
fi

echo
echo "=== Docker cleanup: stopped containers older than 24h ==="
docker container prune -f --filter "until=24h" || true

echo
echo "=== Docker cleanup: unused networks ==="
docker network prune -f || true

echo
echo "=== Docker cleanup: dangling images only ==="
docker image prune -f || true

echo
echo "=== Docker cleanup: unused build cache older than 24h ==="
docker builder prune -f --filter "until=24h" || true

echo
echo "=== Truncating oversized Docker JSON logs >100MB to 50MB ==="
find /var/lib/docker/containers -type f -name '*-json.log' -size +100M -print -exec truncate -s 50M {} \; 2>/dev/null || true

echo
echo "=== Vacuum systemd journal to 7 days ==="
journalctl --vacuum-time=7d >/dev/null 2>&1 || true

echo
echo "=== After cleanup: disk ==="
df -hT | tee "$REPORT_DIR/df-after.txt"

echo
echo "=== After cleanup: docker system df ==="
docker system df -v > "$REPORT_DIR/docker-system-df-after.txt" 2>&1 || true
cat "$REPORT_DIR/docker-system-df-after.txt"

echo
echo "=== After cleanup: major directories ==="
{
  du -sh /opt/ai-station 2>/dev/null || true
  du -sh /srv/ai-station 2>/dev/null || true
  du -sh /srv/ai-station/models 2>/dev/null || true
  du -sh /srv/ai-station/data 2>/dev/null || true
  du -sh /var/lib/docker 2>/dev/null || true
  du -sh /root/.cache 2>/dev/null || true
} | tee "$REPORT_DIR/du-after.txt"

echo
echo "=== Cleanup completed ==="
echo "Report saved to: $REPORT_DIR"
