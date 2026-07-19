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
  curl -s --max-time 30 http://127.0.0.1:8888/health | python3 -m json.tool

  print_header "UI Gateway"
  curl -s --max-time 30 http://127.0.0.1:8890/health | python3 -m json.tool

  print_header "General Model"
  curl -s --max-time 30 http://127.0.0.1:8082/v1/models | python3 -m json.tool

  print_header "Embedding"
  curl -s --max-time 30 http://127.0.0.1:8090/v1/models | python3 -m json.tool

  print_header "SearXNG"
  curl -s --max-time 30 "http://127.0.0.1:8889/search?q=Open%20WebUI&format=json" \
    | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("results", [])))'

  print_header "Apache Tika"
  curl -I --max-time 30 http://127.0.0.1:9998/tika

  print_header "PostgreSQL"
  docker compose exec -T postgres sh -lc '
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT now();"
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dx vector"
  '
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
echo "Verification finished."
