#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/ai-station

MODE="${1:-stack}"

print_header() {
  echo
  echo "================================================"
  echo "$1"
  echo "================================================"
}

verify_stack() {
  print_header "Disk"
  df -h /
  du -sh /srv/ai-station/models/* 2>/dev/null | sort -h || true

  print_header "Docker"
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'

  print_header "Open WebUI"
  curl -I --max-time 30 http://127.0.0.1:3000

  print_header "Gateway"
  curl -s --max-time 30 http://127.0.0.1:8888/health | jq .

  print_header "SearXNG"
  curl -s --max-time 30 "http://127.0.0.1:8889/search?q=Open%20WebUI&format=json" | jq '.results | length'

  print_header "Docling OCR"
  curl -I --max-time 30 http://127.0.0.1:5001/ui

  print_header "PostgreSQL"
  docker exec -i ai-station-postgres-1 sh -lc '
    psql -U "$POSTGRES_USER" -d openwebui -c "SELECT now();"
    psql -U "$POSTGRES_USER" -d openwebui -c "\dx vector"
  '

  print_header "Open WebUI Config"
  docker exec -i ai-station-open-webui-1 python - <<'PY'
import sqlite3

con = sqlite3.connect("/app/backend/data/webui.db")
cur = con.cursor()

for key in [
    "CONTENT_EXTRACTION_ENGINE",
    "DOCLING_SERVER_URL",
    "DOCLING_PARAMS",
    "ENABLE_WEB_SEARCH",
    "WEB_SEARCH_ENGINE",
    "SEARXNG_QUERY_URL",
    "VECTOR_DB",
    "PGVECTOR_DB_URL",
]:
    try:
        row = cur.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
        print(key, "=>", row[0] if row else "MISSING")
    except Exception as e:
        print(key, "=>", repr(e))
PY

  print_header "OCR Models Retained"
  du -sh /srv/ai-station/models/ocr 2>/dev/null || true
  find /srv/ai-station/models/ocr -maxdepth 2 -type d 2>/dev/null | sort
}

case "$MODE" in
  stack)
    verify_stack
    ;;
  *)
    echo "Usage: $0 {stack}"
    exit 2
    ;;
esac

echo
echo "=== Verification done ==="
