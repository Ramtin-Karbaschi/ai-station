# OpenCode integration for AI Station.
# Sourced by scripts/ai after core lifecycle commands are defined.

OPENCODE_CODER_MODEL="Ornith-1.5-35B-Q4_K_M"
OPENCODE_GENERAL_MODEL="Qwen3.8-27B-UD-Q4_K_M"
OPENCODE_REASONING_MODEL="Qwen3.8-27B-Reasoning-UD-Q4_K_M"
OPENCODE_ORNITH_MODEL="Ornith-1.5-35B-Q4_K_M"
OPENCODE_PROJECT_ID="opencode"
OPENCODE_API_KEY_PLACEHOLDER="__AI_STATION_OPENCODE_API_KEY__"
OPENCODE_ALLOWED_MODELS="${OPENCODE_CODER_MODEL},${OPENCODE_GENERAL_MODEL},${OPENCODE_REASONING_MODEL}"
OPENCODE_MANAGER="$ROOT/scripts/opencode_config.py"
OPENCODE_RUNTIME_MANIFEST="$ROOT/config/clients/opencode/runtime.json"

ai_opencode_template_dir() {
  printf '%s\n' "$ROOT/config/clients/opencode"
}

ai_opencode_env_file() {
  printf '%s\n' "$ROOT/projects/${OPENCODE_PROJECT_ID}.env"
}

ai_opencode_developer_user() {
  if [[ -n "${AI_STATION_DEV_USER:-}" ]]; then
    printf '%s\n' "$AI_STATION_DEV_USER"
    return
  fi
  python3 - "$OPENCODE_RUNTIME_MANIFEST" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["developer_user"])
PY
}

ai_opencode_home() {
  if [[ -n "${AI_STATION_OPENCODE_HOME:-}" ]]; then
    printf '%s\n' "$AI_STATION_OPENCODE_HOME"
    return
  fi
  local dev_user home_dir
  dev_user="$(ai_opencode_developer_user)"
  if id "$dev_user" >/dev/null 2>&1; then
    home_dir="$(getent passwd "$dev_user" | cut -d: -f6)"
    printf '%s\n' "$home_dir/.config/opencode"
    return
  fi
  echo "ERROR: WSL developer account '$dev_user' does not exist." >&2
  echo "Run: ai opencode install --create-user --own-project" >&2
  return 1
}

ai_opencode_key_ready() {
  python3 "$OPENCODE_MANAGER" key-ready --env-file "$(ai_opencode_env_file)"
}

ai_opencode_sync_allowlist() {
  local dry_run="${1:-0}"
  local args=(
    sync-allowlist
    --env-file "$(ai_opencode_env_file)"
    --registry "$ROOT/config/registry/projects.yaml"
    --models "$OPENCODE_ALLOWED_MODELS"
  )
  if [[ "$dry_run" -eq 1 ]]; then
    args+=(--dry-run)
  fi
  LITELLM_MASTER_KEY="$(ai_master_key)" python3 "$OPENCODE_MANAGER" "${args[@]}"
}

cmd_opencode() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    install) "$ROOT/scripts/install-opencode-wsl.sh" "$@" ;;
    configure) cmd_opencode_configure "$@" ;;
    doctor) python3 "$ROOT/scripts/opencode_doctor.py" "$@" ;;
    parity) python3 "$ROOT/scripts/opencode_parity.py" "$@" ;;
    run) cmd_opencode_run "$@" ;;
    acceptance) cmd_opencode_acceptance "$@" ;;
    preview) python3 "$ROOT/scripts/opencode_preview.py" "$@" ;;
    audit-session) python3 "$ROOT/scripts/opencode_session_audit.py" "$@" ;;
    desktop) cmd_opencode_desktop "$@" ;;
    use) cmd_opencode_use "$@" ;;
    test) cmd_opencode_test "$@" ;;
    ""|-h|--help|help)
      cat <<'EOF'
Usage:
  ai opencode install [--create-user] [--own-project] [--dry-run]
  ai opencode configure [--dry-run]
  ai opencode doctor [--json]
  ai opencode parity [--live] [--json] [--timeout SECONDS]
  ai opencode run [PROJECT_PATH]
  ai opencode acceptance [--timeout SECONDS] [--keep]
  ai opencode preview start [DIRECTORY] [--port PORT]
  ai opencode preview status|stop
  ai opencode audit-session SESSION.json [--json]
  ai opencode desktop configure|status
  ai opencode use general|coder|reasoning|ornith
  ai opencode test [--model general|coder|reasoning|ornith]
EOF
      ;;
    *)
      echo "Unknown opencode command: $sub" >&2
      echo "Run 'ai opencode --help' for supported commands." >&2
      return 2
      ;;
  esac
}

cmd_opencode_desktop() {
  local action="${1:-}"
  if [[ $# -ne 1 ]] || [[ "$action" != "configure" && "$action" != "status" ]]; then
    echo "Usage: ai opencode desktop configure|status" >&2
    return 2
  fi
  if [[ "$action" == "status" ]]; then
    systemctl is-active --quiet ai-station-opencode.service || {
      echo "FAIL: canonical WSL OpenCode server is not active" >&2
      return 1
    }
    curl -fsS --max-time 5 http://127.0.0.1:4096/global/health >/dev/null || {
      echo "FAIL: canonical WSL OpenCode server health check failed" >&2
      return 1
    }
    echo "OK: canonical WSL OpenCode server is healthy at http://127.0.0.1:4096"
    return
  fi
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: desktop configuration requires root to install the system service" >&2
    return 1
  fi
  install -m 0644 "$ROOT/infra/systemd/ai-station-opencode.service" \
    /etc/systemd/system/ai-station-opencode.service
  systemctl daemon-reload
  systemctl enable --now ai-station-opencode.service
  local windows_script
  windows_script="$(wslpath -w "$ROOT/scripts/configure-opencode-desktop.ps1")"
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$windows_script"
  curl -fsS --max-time 10 http://127.0.0.1:4096/global/health >/dev/null
  echo "OK: Windows Desktop is pinned to the canonical WSL server"
  echo "Restart OpenCode Desktop to apply the connection change"
}

cmd_opencode_configure() {
  local dry_run=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      *) echo "Usage: ai opencode configure [--dry-run]" >&2; return 2 ;;
    esac
  done

  local template_dir dest env_file
  template_dir="$(ai_opencode_template_dir)"
  dest="$(ai_opencode_home)"
  env_file="$(ai_opencode_env_file)"

  curl -fsS --max-time 5 "http://127.0.0.1:4000/health/liveliness" >/dev/null || {
    echo "ERROR: LiteLLM gateway is not healthy on :4000" >&2
    return 1
  }
  echo "OK: LiteLLM liveliness on :4000"

  if ! ai_opencode_key_ready; then
    if [[ "$dry_run" -eq 1 ]]; then
      echo "DRY-RUN: would create project $OPENCODE_PROJECT_ID"
    else
      cmd_projects_create "$OPENCODE_PROJECT_ID" --models "$OPENCODE_ALLOWED_MODELS"
    fi
  else
    echo "OK: OpenCode project credentials are present"
  fi
  ai_opencode_sync_allowlist "$dry_run"

  local render_args=(
    render
    --template-dir "$template_dir"
    --dest "$dest"
    --env-file "$env_file"
    --placeholder "$OPENCODE_API_KEY_PLACEHOLDER"
  )
  if [[ "$dry_run" -eq 1 ]]; then
    render_args+=(--dry-run)
  fi
  python3 "$OPENCODE_MANAGER" "${render_args[@]}"

  if [[ "$dry_run" -eq 0 ]]; then
    local dev_user dev_home
    dev_user="$(ai_opencode_developer_user)"
    dev_home="$(getent passwd "$dev_user" | cut -d: -f6)"
    if [[ "$dest" == "$dev_home/"* ]]; then
      chown -R "$dev_user:$dev_user" "$dest"
      find "$dest" -type d -exec chmod 0700 {} +
      find "$dest" -type f -exec chmod 0600 {} +
      echo "OK: WSL config belongs to non-root user $dev_user"
    fi
    echo "Launch: ai opencode run $ROOT"
    echo "Verify: ai opencode acceptance"
  fi
}

cmd_opencode_run() {
  local project="${1:-$ROOT}"
  if [[ $# -gt 1 || ! -d "$project" ]]; then
    echo "Usage: ai opencode run [PROJECT_PATH]" >&2
    return 2
  fi
  project="$(realpath "$project")"
  local dev_user dev_home
  dev_user="$(ai_opencode_developer_user)"
  dev_home="$(getent passwd "$dev_user" 2>/dev/null | cut -d: -f6 || true)"
  if [[ -z "$dev_home" || ! -x /usr/local/bin/opencode ]]; then
    echo "ERROR: WSL OpenCode developer runtime is not installed" >&2
    return 1
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    exec runuser -u "$dev_user" -- env \
      HOME="$dev_home" \
      OPENCODE_EXPERIMENTAL_LSP_TOOL=true \
      /bin/bash -c 'cd -- "$1" && exec /usr/local/bin/opencode .' _ "$project"
  fi
  if [[ "$(id -un)" != "$dev_user" ]]; then
    echo "ERROR: run OpenCode as $dev_user, never as root" >&2
    return 1
  fi
  cd "$project"
  exec env OPENCODE_EXPERIMENTAL_LSP_TOOL=true /usr/local/bin/opencode .
}

cmd_opencode_acceptance() {
  local dev_user dev_home
  dev_user="$(ai_opencode_developer_user)"
  dev_home="$(getent passwd "$dev_user" 2>/dev/null | cut -d: -f6 || true)"
  if [[ -z "$dev_home" || ! -x /usr/local/bin/opencode ]]; then
    echo "ERROR: WSL OpenCode developer runtime is not installed" >&2
    return 1
  fi
  if [[ "$(id -u)" -eq 0 ]]; then
    runuser -u "$dev_user" -- env \
      HOME="$dev_home" \
      PATH="/usr/local/bin:/usr/bin:/bin" \
      OPENCODE_EXPERIMENTAL_LSP_TOOL=true \
      python3 "$ROOT/scripts/opencode_acceptance.py" "$@"
    return
  fi
  if [[ "$(id -un)" != "$dev_user" ]]; then
    echo "ERROR: run acceptance as $dev_user, never as root" >&2
    return 1
  fi
  OPENCODE_EXPERIMENTAL_LSP_TOOL=true \
    python3 "$ROOT/scripts/opencode_acceptance.py" "$@"
}

ai_opencode_apply_profile() {
  local profile="${1:-}"
  case "$profile" in
    general|coder|reasoning|ornith) ;;
    *) echo "Usage: ai opencode use general|coder|reasoning|ornith" >&2; return 2 ;;
  esac
  local config
  config="$(ai_opencode_home)/opencode.jsonc"
  if [[ ! -f "$config" ]]; then
    echo "ERROR: missing $config; run ai opencode configure" >&2
    return 1
  fi
  python3 "$OPENCODE_MANAGER" apply-profile --config "$config" --profile "$profile"
  local dev_user
  dev_user="$(ai_opencode_developer_user)"
  chown "$dev_user:$dev_user" "$config"
}

cmd_opencode_use() {
  local profile="${1:-}"
  if [[ $# -ne 1 ]]; then
    echo "Usage: ai opencode use general|coder|reasoning|ornith" >&2
    return 2
  fi
  ai_opencode_apply_profile "$profile"
  echo "Switching heavy GPU profile -> $profile"
  cmd_models_use "$profile"
}

cmd_opencode_test() {
  local profile="coder"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --model) profile="${2:-}"; shift 2 ;;
      *) echo "Usage: ai opencode test [--model PROFILE]" >&2; return 2 ;;
    esac
  done
  local public runtime_port
  case "$profile" in
    general) public="$OPENCODE_GENERAL_MODEL"; runtime_port=8082 ;;
    coder) public="$OPENCODE_CODER_MODEL"; runtime_port=8083 ;;
    reasoning) public="$OPENCODE_REASONING_MODEL"; runtime_port=8084 ;;
    ornith) public="$OPENCODE_ORNITH_MODEL"; runtime_port=8086 ;;
    *) echo "Unknown OpenCode profile: $profile" >&2; return 2 ;;
  esac

  local config
  config="$(ai_opencode_home)/opencode.jsonc"
  python3 "$OPENCODE_MANAGER" validate \
    --config "$config" --template-dir "$(ai_opencode_template_dir)"
  curl -fsS --max-time 5 "http://127.0.0.1:4000/health/liveliness" >/dev/null || {
    echo "FAIL: LiteLLM health" >&2
    return 1
  }
  if ! curl -fsS --max-time 5 "http://127.0.0.1:$runtime_port/v1/models" >/dev/null; then
    echo "$profile runtime is not active; switching the heavy profile"
    cmd_models_use "$profile"
  fi
  python3 "$OPENCODE_MANAGER" probe \
    --env-file "$(ai_opencode_env_file)" \
    --profile "$profile" \
    --model "$public"
}
