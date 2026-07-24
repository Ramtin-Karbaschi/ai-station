#!/usr/bin/env bash
# Single Windows↔WSL control plane for AI Station.
set -Eeuo pipefail

ROOT="/opt/ai-station"
cd "$ROOT"

ACTION="${1:-}"
ARG2="${2:-}"
ARG3="${3:-}"

require_tools() {
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

ai_bin() {
  "$ROOT/scripts/ai" "$@"
}

case "$ACTION" in
  start)
    require_tools
    ensure_docker
    echo "Starting AI Station..."
    "$ROOT/scripts/ai-station-user-start.sh"
    ;;

  stop)
    require_tools
    ensure_docker
    echo "Stopping AI Station..."
    "$ROOT/scripts/ai-station-user-stop.sh"
    ;;

  restart)
    require_tools
    ensure_docker
    echo "Restarting AI Station..."
    "$ROOT/scripts/ai-station-user-stop.sh" || true
    "$ROOT/scripts/ai-station-user-start.sh"
    ;;

  stop-heavy-models)
    require_tools
    ensure_docker
    echo "Stopping heavy LLM containers..."
    ai_bin models stop
    ;;

  status)
    require_tools
    ai_bin status
    ;;

  verify)
    require_tools
    ensure_docker
    ai_bin verify
    echo
    curl -fsS --max-time 5 http://127.0.0.1:4000/health/liveliness || true
    echo
    curl -fsS --max-time 5 http://127.0.0.1:8888/health 2>/dev/null | python3 -m json.tool || true
    curl -fsS --max-time 5 http://127.0.0.1:8890/health 2>/dev/null | python3 -m json.tool || true
    ;;

  model-use)
    require_tools
    ensure_docker
    if [[ -z "$ARG2" ]]; then
      echo "Usage: $0 model-use <general|coder|reasoning|vision>"
      exit 2
    fi
    ai_bin models use "$ARG2"
    ;;

  models-list)
    ai_bin models list
    echo
    ai_bin models active
    ;;

  projects-list)
    ai_bin projects list
    ;;

  projects-create)
    require_tools
    ensure_docker
    if [[ -z "$ARG2" ]]; then
      echo "Usage: $0 projects-create <project-id> [models-csv]"
      exit 2
    fi
    MODELS="${ARG3:-local-general,local-embedding}"
    ai_bin projects create "$ARG2" --models "$MODELS"
    ;;

  projects-show)
    if [[ -z "$ARG2" ]]; then
      echo "Usage: $0 projects-show <project-id>"
      exit 2
    fi
    ai_bin projects show "$ARG2"
    echo
    ENV_FILE="$ROOT/projects/${ARG2}.env"
    if [[ -f "$ENV_FILE" ]]; then
      echo "=== Credentials file (secrets redacted) ==="
      sed -E 's/(LLM_API_KEY=).*/\1***REDACTED***/' "$ENV_FILE"
      echo
      echo "Full secret file (WSL): $ENV_FILE"
      echo "Windows path: \\\\wsl.localhost\\Ubuntu\\opt\\ai-station\\projects\\${ARG2}.env"
    fi
    ;;

  projects-revoke)
    require_tools
    ensure_docker
    if [[ -z "$ARG2" ]]; then
      echo "Usage: $0 projects-revoke <project-id>"
      exit 2
    fi
    ai_bin projects revoke "$ARG2"
    ;;

  api-info)
    cat <<EOF
AI Station Application API
==========================
Base URL (host):   http://127.0.0.1:4000/v1
Base URL (Docker): http://llm-gateway:4000/v1
Docker network:    ai-platform (external)
Admin / health:    http://127.0.0.1:4000/health/liveliness
LiteLLM UI:        http://127.0.0.1:4000/ui

Stable model aliases:
  local-general
  local-coder
  local-reasoning
  local-vision
  local-embedding
  local-reranker

Create a project key:
  ai projects create <id> --models local-general,local-embedding

Python example:
  from openai import OpenAI
  client = OpenAI(base_url="http://127.0.0.1:4000/v1", api_key="...")
EOF
    echo
    if [[ -f "$ROOT/secrets/litellm_ui_credentials.txt" ]]; then
      echo "=== LiteLLM Admin UI login ==="
      cat "$ROOT/secrets/litellm_ui_credentials.txt"
      echo
    else
      echo "LiteLLM UI default login: username=admin , password=<LITELLM_MASTER_KEY from .env>"
      echo
    fi
    ai_bin projects list
    ;;

  litellm-ui-credentials)
    if [[ -f "$ROOT/secrets/litellm_ui_credentials.txt" ]]; then
      cat "$ROOT/secrets/litellm_ui_credentials.txt"
    else
      echo "No secrets/litellm_ui_credentials.txt found."
      echo "Default: username=admin , password=value of LITELLM_MASTER_KEY in .env"
    fi
    ;;

  reset-webui-password)
    require_tools
    ensure_docker
    "$ROOT/scripts/reset-openwebui-password.sh" "${ARG2:-}" "${ARG3:-}"
    ;;

  logs|logs-all)
    echo "=== LiteLLM gateway (last 80 lines) ==="
    docker logs --tail 80 ai-station-llm-gateway 2>&1 || true
    echo
    echo "=== Open WebUI (last 80 lines) ==="
    docker logs --tail 80 ai-station-open-webui-1 2>&1 || true
    echo
    echo "=== Host gateway journal (last 60 lines) ==="
    journalctl -u ai-station-gateway -n 60 --no-pager 2>&1 || true
    echo
    echo "=== UI gateway journal (last 40 lines) ==="
    journalctl -u ai-station-ui-gateway -n 40 --no-pager 2>&1 || true
    ;;

  logs-gateway)
    echo "=== LiteLLM gateway (last 120 lines) ==="
    docker logs --tail 120 ai-station-llm-gateway 2>&1 || true
    echo
    echo "=== ai-station-gateway (last 80 lines) ==="
    journalctl -u ai-station-gateway -n 80 --no-pager || true
    echo
    echo "=== ai-station-ui-gateway (last 40 lines) ==="
    journalctl -u ai-station-ui-gateway -n 40 --no-pager || true
    ;;

  logs-webui)
    docker logs --tail 120 ai-station-open-webui-1 2>&1 || true
    ;;

  logs-tika|logs-ocr)
    docker logs --tail 120 ai-station-tika 2>&1 || true
    ;;

  logs-general)
    docker logs --tail 120 ai-station-llm-general 2>&1 \
      || docker logs --tail 120 ai-station-llm-general-1 2>&1 \
      || true
    ;;

  backup)
    require_tools
    "$ROOT/scripts/backup.sh"
    ;;

  vscode)
    if command -v code >/dev/null 2>&1; then
      code "$ROOT"
    else
      echo "VS Code CLI (code) is not installed inside WSL."
      echo "Open from Windows: \\\\wsl.localhost\\Ubuntu\\opt\\ai-station"
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

  help|"")
    cat <<'HELP'
Usage: ai-station-manager-action.sh <action> [args]

Platform:
  start | stop | restart | status | verify | backup | disk

Models:
  models-list
  model-use <general|coder|reasoning|vision>
  stop-heavy-models

API / Projects:
  api-info
  projects-list
  projects-create <id> [models-csv]
  projects-show <id>
  projects-revoke <id>
  reset-webui-password [email] [password]
  litellm-ui-credentials

Logs:
  logs | logs-gateway | logs-webui | logs-tika | logs-general

Dev:
  vscode | git
HELP
    ;;

  *)
    echo "Unknown action: $ACTION"
    echo "Run: $0 help"
    exit 2
    ;;
esac
