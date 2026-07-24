#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="/opt/ai-station/support/state-${STAMP}"
mkdir -p "$OUT"

redact() {
  sed -E \
    -e 's#(postgresql://[^:]+:)[^@]+@#\1***@#g' \
    -e 's#(password|passwd|secret|token|api_key|apikey|key)=([^[:space:]]+)#\1=***#Ig' \
    -e 's#(PASSWORD|SECRET|TOKEN|API_KEY|OPENAI_API_KEY|OPENAI_API_KEYS):[[:space:]]*.*#\1: "***"#g' \
    -e 's#(DATABASE_URL: )[^\r\n]+#\1"***"#g' \
    -e 's#(PGVECTOR_DB_URL: )[^\r\n]+#\1"***"#g'
}

run() {
  local name="$1"
  shift
  echo ">>> $name"
  {
    echo "### $name"
    echo "\$ $*"
    "$@" 2>&1 || true
  } | redact | tee "$OUT/${name}.txt" >/dev/null
}

echo "AI Station inventory: $OUT"
date -Iseconds > "$OUT/timestamp.txt"

run "01-os-release" bash -lc 'cat /etc/os-release; echo; uname -a'
run "02-wsl" bash -lc 'wsl.exe -l -v 2>/dev/null || true'
run "03-windows-disk" bash -lc 'powershell.exe -NoProfile -Command "Get-PSDrive C | Format-List *" 2>/dev/null || true'
run "04-cpu-memory" bash -lc 'lscpu; echo; free -h'
run "05-gpu" bash -lc 'nvidia-smi || true'
run "06-disk" bash -lc 'df -hT; echo; lsblk -f; echo; mount | sort'
run "07-major-du" bash -lc '
du -sh /opt/ai-station 2>/dev/null || true
du -sh /srv/ai-station 2>/dev/null || true
du -sh /srv/ai-station/models 2>/dev/null || true
du -sh /srv/ai-station/data 2>/dev/null || true
du -sh /var/lib/docker 2>/dev/null || true
du -sh /root/.cache 2>/dev/null || true
'

run "08-docker-version" docker version
run "09-docker-info" docker info
run "10-docker-ps" bash -lc 'docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"'
run "11-docker-images" bash -lc 'docker images --digests --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.Digest}}"'
run "12-docker-volumes" bash -lc 'docker volume ls'
run "13-docker-networks" bash -lc 'docker network ls'
run "14-docker-system-df" bash -lc 'docker system df -v'
run "15-compose-files" bash -lc 'ls -lah compose*.yml .env* 2>/dev/null || true'
run "16-compose-config-redacted" bash -lc './scripts/compose-ai-station.sh --profile console --profile rag --profile search --profile tika --profile llm-general config'

run "17-systemd-units" bash -lc '
systemctl status docker --no-pager -l || true
systemctl status ai-station-gateway --no-pager -l || true
systemctl status ai-station-ui-gateway --no-pager -l || true
'
run "18-systemd-logs" bash -lc '
journalctl -u ai-station-gateway --since "3 hours ago" --no-pager -l || true
echo "---- UI GATEWAY ----"
journalctl -u ai-station-ui-gateway --since "3 hours ago" --no-pager -l || true
'

run "19-endpoints" bash -lc '
echo "Open WebUI"; curl -I --max-time 15 http://127.0.0.1:3000 || true
echo "AI Gateway"; curl -s --max-time 15 http://127.0.0.1:8888/v1/models | head -c 2000 || true; echo
echo "UI Gateway"; curl -s --max-time 15 http://127.0.0.1:8890/v1/models | jq . || true
echo "SearXNG"; curl -s --max-time 15 "http://127.0.0.1:8889/search?q=test&format=json" | jq "{result_count: (.results|length)}" || true
echo "Tika"; curl -s --max-time 15 http://127.0.0.1:9998/tika || true
'

run "20-tika" bash -lc '
docker exec -i ai-station-tika sh -lc "java -version; echo; tesseract --version; echo; tesseract --list-langs | sort" || true
'

run "21-openwebui-env" bash -lc '
docker exec -i ai-station-open-webui-1 sh -lc "
printenv | grep -E \"DATABASE|VECTOR_DB|PGVECTOR|REDIS|OPENAI|CONTENT_EXTRACTION|TIKA|RAG|WEB_SEARCH|SEARXNG|HF_HUB|WHISPER|AUDIO_STT|DEFAULT_MODEL\" | sort
" || true
'

run "22-openwebui-logs" bash -lc '
docker logs --tail=500 ai-station-open-webui-1 2>&1 | grep -Ei "error|traceback|failed|warning|tika|rag|upload|xlsx|audio|stt|whisper|model|postgres|redis|timeout" || true
'

run "23-postgres-openwebui-config" bash -lc '
docker exec -i ai-station-postgres-1 sh -lc '\''psql -U "$POSTGRES_USER" -d openwebui'\'' <<'\''SQL'\''
SELECT key, value
FROM config
WHERE key ILIKE '\''%OPENAI%'\''
   OR key ILIKE '\''%MODEL%'\''
   OR key ILIKE '\''%RAG%'\''
   OR key ILIKE '\''%TIKA%'\''
   OR key ILIKE '\''%WHISPER%'\''
   OR key ILIKE '\''%AUDIO_STT%'\''
   OR key ILIKE '\''%WEB_SEARCH%'\''
   OR key ILIKE '\''%SEARXNG%'\''
   OR key IN ('\''CONTENT_EXTRACTION_ENGINE'\'','\''TIKA_SERVER_URL'\'','\''DEFAULT_MODELS'\'','\''DEFAULT_PINNED_MODELS'\'')
ORDER BY key;

SELECT id, name, base_model_id, is_active, meta, params
FROM model
ORDER BY id;
SQL
'

run "24-postgres-size" bash -lc '
docker exec -i ai-station-postgres-1 sh -lc '\''psql -U "$POSTGRES_USER" -d openwebui'\'' <<'\''SQL'\''
SELECT pg_size_pretty(pg_database_size(current_database())) AS openwebui_db_size;

SELECT schemaname, relname, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 25;
SQL
'

run "25-model-registry" bash -lc '
find /srv/ai-station/models -maxdepth 3 -type f -printf "%s\t%p\n" 2>/dev/null | sort -nr | head -100
echo
cat /srv/ai-station/models/ai-station-model-registry.json 2>/dev/null || true
'

run "26-whisper-local" bash -lc '
docker exec -i ai-station-open-webui-1 sh -lc "
du -sh /app/backend/data/cache/whisper/models/faster-whisper-large-v3 2>/dev/null || true
find /app/backend/data/cache/whisper/models/faster-whisper-large-v3 -maxdepth 1 -type f -printf \"%s  %f\n\" 2>/dev/null | sort -nr || true
"
'

run "27-project-tree" bash -lc '
find /opt/ai-station -maxdepth 3 -type f \
  ! -path "*/.git/*" \
  ! -path "*/node_modules/*" \
  -printf "%TY-%Tm-%Td %TH:%TM  %s  %p\n" 2>/dev/null | sort
'

run "28-backups-and-temp-leftovers" bash -lc '
echo "Backups:"
find /opt/ai-station -type f \( -name "*.bak*" -o -name "*.old*" -o -name "*.backup*" \) -printf "%TY-%Tm-%Td %TH:%TM  %s  %p\n" 2>/dev/null | sort || true
echo
echo "Incomplete/partial files:"
find /opt/ai-station /srv/ai-station /root/.cache -type f \( -name "*.incomplete" -o -name "*.partial" -o -name "*.part" \) -printf "%TY-%Tm-%Td %TH:%TM  %s  %p\n" 2>/dev/null | sort || true
'

run "29-ai-station-scripts-head" bash -lc '
for f in scripts/*.sh apps/ui-gateway/*.py; do
  echo "===== $f ====="
  sed -n "1,220p" "$f" 2>/dev/null || true
done
'

cat > "$OUT/SUMMARY.txt" <<EOF
AI Station State Bundle
Generated: $(date -Iseconds)
Path: $OUT

Send these first:
- 10-docker-ps.txt
- 14-docker-system-df.txt
- 16-compose-config-redacted.txt
- 19-endpoints.txt
- 21-openwebui-env.txt
- 22-openwebui-logs.txt
- 23-postgres-openwebui-config.txt
- 25-model-registry.txt
- 28-backups-and-temp-leftovers.txt
EOF

tar -czf "/opt/ai-station/support/ai-station-state-${STAMP}.tar.gz" -C "$OUT" .

echo
echo "=== Inventory completed ==="
echo "Directory: $OUT"
echo "Archive: /opt/ai-station/support/ai-station-state-${STAMP}.tar.gz"
echo
cat "$OUT/SUMMARY.txt"
