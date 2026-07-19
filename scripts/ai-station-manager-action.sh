#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/opt/ai-station"
cd "$ROOT"

ACTION="${1:-}"

require_root_tools() {
  command -v docker >/dev/null 2>&1 || {
    echo "ERROR: docker is not available inside WSL."
    exit 1
  }
  command -v systemctl >/dev/null 2>&1 || {
    echo "ERROR: systemctl is not available. Enable systemd in /etc/wsl.conf."
    exit 1
  }
}

ensure_docker() {
  systemctl start docker >/dev/null 2>&1 || true
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not reachable from WSL."
    echo "Start Docker Desktop on Windows, then retry."
    exit 1
  fi
}

case "$ACTION" in
  start)
    require_root_tools
    ensure_docker
    echo "Starting AI Station..."
    ./scripts/start.sh
    ;;

  stop)
    require_root_tools
    ensure_docker
    echo "Stopping AI Station..."
    ./scripts/stop.sh
    ;;

  stop-heavy-models)
    require_root_tools
    ensure_docker
    echo "Stopping heavy LLM containers..."
    ./scripts/stop-ai-station-models.sh
    ;;

  status)
    require_root_tools
    ./scripts/status.sh
    echo
    ./scripts/status-ai-station.sh
    ;;

  logs-gateway)
    echo "=== ai-station-gateway (last 120 lines) ==="
    journalctl -u ai-station-gateway -n 120 --no-pager || true
    echo
    echo "=== ai-station-ui-gateway (last 80 lines) ==="
    journalctl -u ai-station-ui-gateway -n 80 --no-pager || true
    ;;

  logs-webui)
    echo "=== open-webui (last 120 lines) ==="
    docker logs --tail 120 ai-station-open-webui-1 2>&1 || true
    ;;

  logs-tika|logs-ocr)
    echo "=== tika (last 120 lines) ==="
    docker logs --tail 120 ai-station-tika 2>&1 || true
    ;;

  logs-general)
    echo "=== llm-general (last 120 lines) ==="
    docker logs --tail 120 ai-station-llm-general-1 2>&1 || true
    ;;

  vscode)
    if command -v code >/dev/null 2>&1; then
      code "$ROOT"
    else
      echo "VS Code CLI (code) is not installed inside WSL."
      echo "Open the folder from Windows instead:"
      echo "  \\\\wsl.localhost\\Ubuntu\\opt\\ai-station"
    fi
    ;;

  git)
    git -C "$ROOT" status -sb
    echo
    git -C "$ROOT" log -5 --oneline
    ;;

  disk)
    echo "=== Filesystem ==="
    df -hT / /srv 2>/dev/null || df -hT /
    echo
    echo "=== Models ==="
    du -sh /srv/ai-station/models/* 2>/dev/null | sort -h || true
    echo
    echo "=== Docker ==="
    docker system df || true
    ;;

  verify)
    require_root_tools
    ensure_docker
    ./scripts/verify.sh
    echo
    curl -fsS --max-time 5 http://127.0.0.1:8888/health | python3 -m json.tool || true
    curl -fsS --max-time 5 http://127.0.0.1:8890/health | python3 -m json.tool || true
    ;;

  help|"")
    cat <<'HELP'
Usage: ai-station-manager-action.sh <action>

Actions:
  start
  stop
  stop-heavy-models
  status
  verify
  logs-gateway
  logs-webui
  logs-tika
  logs-general
  vscode
  git
  disk
HELP
    ;;

  *)
    echo "Unknown action: $ACTION"
    echo "Run: $0 help"
    exit 2
    ;;
esac
