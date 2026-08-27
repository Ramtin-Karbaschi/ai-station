# n8n optional workflow client for AI Station (ADR-021).
# Sourced by scripts/ai. CPU-only; calls LiteLLM, never llama.cpp ports.

N8N_RUNTIME_DIR="${AI_STATION_DATA:-/srv/ai-station}/runtime/n8n"
N8N_HEALTH_URL="http://127.0.0.1:5678/healthz"
N8N_UI_URL="http://127.0.0.1:5678"
N8N_PROJECT_ID="n8n"
N8N_PROJECT_MODELS="Qwen3.8-27B-UD-Q4_K_M,Ornith-1.5-35B-Q4_K_M,Qwen3-Embedding-8B-Q4_K_M"

ai_n8n_usage() {
  cat <<'EOF'
Usage:
  ai n8n start [--dry-run]
  ai n8n stop
  ai n8n status
  ai n8n configure
  ai n8n uninstall [--purge] [--confirm] [--dry-run]

Optional CPU workflow client (http://127.0.0.1:5678). Not started by ai start.
Workflows must call LiteLLM at http://llm-gateway:4000/v1 (never :8888).
EOF
}

cmd_n8n() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    start) cmd_n8n_start "$@" ;;
    stop) cmd_n8n_stop "$@" ;;
    status) cmd_n8n_status ;;
    configure) cmd_n8n_configure ;;
    uninstall) cmd_n8n_uninstall "$@" ;;
    -h|--help|help|"") ai_n8n_usage ;;
    *)
      echo "Unknown n8n command: $sub" >&2
      ai_n8n_usage >&2
      exit 2
      ;;
  esac
}

cmd_n8n_start() {
  cmd_provider_start n8n "$@"
}

cmd_n8n_stop() {
  cmd_provider_stop n8n
}

cmd_n8n_status() {
  echo "url:     $N8N_UI_URL"
  echo "health:  $N8N_HEALTH_URL"
  echo "data:    $N8N_RUNTIME_DIR"
  if curl -fsS --max-time 3 "$N8N_HEALTH_URL" >/dev/null 2>&1; then
    echo "state:   healthy"
  else
    echo "state:   down (run: ai n8n start)"
  fi
  local env_path="$ROOT/projects/${N8N_PROJECT_ID}.env"
  if [[ -f "$env_path" ]]; then
    echo "project: $env_path"
  else
    echo "project: missing (run: ai n8n configure)"
  fi
}

cmd_n8n_configure() {
  local env_path="$ROOT/projects/${N8N_PROJECT_ID}.env"
  if [[ -f "$env_path" ]]; then
    echo "Project ${N8N_PROJECT_ID} already exists: ${env_path}"
  else
    cmd_projects_create "$N8N_PROJECT_ID" --models "$N8N_PROJECT_MODELS"
  fi
  cat <<EOF
LiteLLM credential in n8n (HTTP Header Auth):
  Name:  Authorization
  Value: Bearer <LLM_API_KEY from ${env_path}>
HTTP Request URL from the n8n container:
  http://llm-gateway:4000/v1/chat/completions
Canonical model example:
  Qwen3.8-27B-UD-Q4_K_M
Import station templates from:
  ${ROOT}/config/clients/n8n/workflows/
UI: ${N8N_UI_URL}
EOF
}

cmd_n8n_uninstall() {
  local dry_run=0 purge=0 confirm=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      --purge) purge=1; shift ;;
      --confirm) confirm=1; shift ;;
      *)
        echo "Unknown argument: $1" >&2
        echo "Usage: ai n8n uninstall [--purge] [--confirm] [--dry-run]" >&2
        exit 2
        ;;
    esac
  done
  if [[ "$dry_run" -eq 1 ]]; then
    echo "DRY-RUN: would stop and remove the n8n container"
    if [[ "$purge" -eq 1 ]]; then
      echo "DRY-RUN: would delete $N8N_RUNTIME_DIR"
    fi
    return 0
  fi
  cmd_provider_stop n8n
  if [[ "$purge" -eq 1 ]]; then
    if [[ "$confirm" -ne 1 ]]; then
      echo "ERROR: --purge requires --confirm (deletes $N8N_RUNTIME_DIR)" >&2
      exit 2
    fi
    rm -rf "$N8N_RUNTIME_DIR"
    echo "OK: purged n8n runtime data"
  fi
}
