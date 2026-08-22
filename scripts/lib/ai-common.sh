#!/usr/bin/env bash
# Shared helpers for AI Station platform CLI.
set -Eeuo pipefail

AI_STATION_ROOT="${AI_STATION_ROOT:-/opt/ai-station}"
AI_STATION_DATA="${AI_STATION_DATA:-/srv/ai-station}"
AI_STATE_DIR="${AI_STATE_DIR:-$AI_STATION_DATA/runtime}"
AI_ACTIVE_PROFILE_FILE="${AI_ACTIVE_PROFILE_FILE:-$AI_STATE_DIR/active-heavy-profile}"

HEAVY_PROFILES=(general coder reasoning vision ornith)
OPTIONAL_PROFILES=(reranker)
EXPERIMENTAL_GPU_OVERLAYS=(
  "comfyui-experimental:compose.comfyui.experimental.yaml:comfyui-experimental"
  "sglang-experimental:compose.sglang.experimental.yaml:sglang-experimental"
)

ai_root() {
  cd "$AI_STATION_ROOT"
}

ai_compose() {
  ai_root
  "$AI_STATION_ROOT/scripts/compose-ai-station.sh" "$@"
}

ai_load_env_value() {
  local key="$1"
  python3 - "$key" <<'PY'
import sys
from pathlib import Path
key = sys.argv[1]
path = Path("/opt/ai-station/.env")
if not path.exists():
    raise SystemExit(0)
for line in path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k.strip() == key:
        print(v.strip().strip('"').strip("'"))
        break
PY
}

ai_master_key() {
  ai_load_env_value LITELLM_MASTER_KEY
}

ai_wait_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-180}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      echo "OK: $label"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: $label not ready: $url" >&2
  return 1
}

ai_compose_container_id() {
  local service="$1"
  ai_compose ps -q "$service" 2>/dev/null | tr -d '[:space:]'
}

ai_wait_compose_service() {
  local service="$1"
  local desired="${2:-running}"
  local attempts="${3:-180}"
  local i cid state health

  for ((i = 1; i <= attempts; i++)); do
    cid="$(ai_compose_container_id "$service")"
    if [[ -n "$cid" ]]; then
      state="$(
        docker inspect -f '{{.State.Status}}' "$cid" 2>/dev/null || true
      )"
      health="$(
        docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$cid" 2>/dev/null || true
      )"
      case "$desired" in
        running)
          if [[ "$state" == "running" ]]; then
            echo "OK: compose service running ($service)"
            return 0
          fi
          ;;
        healthy)
          if [[ "$state" == "running" && "$health" == "healthy" ]]; then
            echo "OK: compose service healthy ($service)"
            return 0
          fi
          ;;
        *)
          echo "ERROR: unknown desired compose state '$desired'" >&2
          return 1
          ;;
      esac
    fi
    sleep 2
  done

  echo "ERROR: compose service not ${desired}: ${service}" >&2
  if [[ -n "$cid" ]]; then
    docker inspect -f 'state={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' "$cid" 2>/dev/null >&2 || true
  fi
  return 1
}

ai_ensure_network() {
  if ! docker network inspect ai-platform >/dev/null 2>&1; then
    docker network create ai-platform >/dev/null
    echo "Created docker network: ai-platform"
  fi
}

ai_ensure_docker() {
  systemctl start docker >/dev/null 2>&1 || true
  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not reachable from WSL." >&2
    echo "Start Docker Desktop on Windows, then retry." >&2
    return 1
  fi
}

ai_dump_published_ports() {
  echo "--- loopback listeners ---" >&2
  ss -lntp 2>/dev/null | grep -E \
    ':(3000|5432|6379|8082|8083|8084|8085|8086|8090|8091|8888|8889|8890|9998)\b' >&2 || true
  echo "--- ai-station containers ---" >&2
  docker ps -a --filter name=ai-station \
    --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' >&2 || true
}

# Docker Desktop on WSL2 sometimes returns HTTP 500 from /forwards/expose
# while publishing 127.0.0.1 ports (Tika :9998 is a frequent hit). Retry
# after dropping containers stuck in "Created".
ai_retry_compose() {
  local attempt
  for attempt in 1 2 3; do
    if ai_compose "$@"; then
      return 0
    fi
    echo "WARNING: docker compose failed (attempt ${attempt}/3)." >&2
    if (( attempt < 3 )); then
      echo "Retrying; Docker Desktop WSL port forwarding can return HTTP 500." >&2
      docker ps -aq --filter name=ai-station --filter status=created \
        | xargs -r docker rm -f >/dev/null 2>&1 || true
      sleep $((attempt * 3))
    fi
  done
  echo "ERROR: docker compose failed after 3 attempts: $*" >&2
  echo "If the log mentioned /forwards/expose or ports are not available:" >&2
  echo "  restart Docker Desktop on Windows, wait until it is ready, then Start again." >&2
  ai_dump_published_ports
  return 1
}

ai_stop_experimental_gpu_overlays() {
  local root="${AI_STATION_ROOT:-/opt/ai-station}"
  local entry profile overlay service
  (
    cd "$root"
    for entry in "${EXPERIMENTAL_GPU_OVERLAYS[@]}"; do
      IFS=':' read -r profile overlay service <<<"$entry"
      env -u COMPOSE_FILE docker compose \
        --project-name "${COMPOSE_PROJECT_NAME:-ai-station}" \
        --env-file .env \
        -f compose.yml -f "$overlay" \
        --profile "$profile" \
        stop "$service" 2>/dev/null || true
    done
  )
}

ai_prepare_comfyui_runtime_dirs() {
  local data="${AI_STATION_DATA:-/srv/ai-station}"
  mkdir -p \
    "$data/runtime/comfyui/input" \
    "$data/runtime/comfyui/output" \
    "$data/runtime/comfyui/user/default/workflows" \
    "$data/models/comfyui/diffusion_models" \
    "$data/models/comfyui/text_encoders" \
    "$data/models/comfyui/vae" \
    "$data/models/comfyui/loras"
  python3 - "$data/runtime/comfyui/user/default/comfy.settings.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
data = {}
if path.is_file():
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    except json.JSONDecodeError:
        data = {}
data.setdefault("Comfy.TutorialCompleted", True)
data.setdefault("Comfy.RightSidePanel.IsOpen", True)
path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")
PY
}

ai_last_or_default_profile() {
  local profile
  profile="$(ai_active_heavy_profile 2>/dev/null || true)"
  profile="$(tr -d '[:space:]' <<<"$profile")"
  case "$profile" in
    general|coder|reasoning|vision|ornith) printf '%s\n' "$profile" ;;
    *) printf '%s\n' "general" ;;
  esac
}

ai_ensure_state_dir() {
  mkdir -p "$AI_STATE_DIR"
}

# Serialize start/stop/restart so concurrent Manager/Desktop actions cannot
# tear down postgres/redis while another start is still bringing the stack up.
AI_LIFECYCLE_LOCK_FILE="${AI_LIFECYCLE_LOCK_FILE:-$AI_STATE_DIR/lifecycle.lock}"

ai_lifecycle_lock() {
  local action="${1:-lifecycle}"
  ai_ensure_state_dir
  exec {AI_LIFECYCLE_LOCK_FD}>"$AI_LIFECYCLE_LOCK_FILE"
  if ! flock -n "$AI_LIFECYCLE_LOCK_FD"; then
    local holder
    holder="$(head -n 1 "$AI_LIFECYCLE_LOCK_FILE" 2>/dev/null || true)"
    echo "ERROR: another AI Station ${action} is already in progress." >&2
    if [[ -n "$holder" ]]; then
      echo "  lock holder: $holder" >&2
    fi
    echo "Close other Manager/Desktop start-stop windows and retry." >&2
    exit 4
  fi
  printf '%s action=%s pid=%s ppid=%s parent=%s\n' \
    "$(date -Is)" \
    "$action" \
    "$$" \
    "$PPID" \
    "$(tr '\0' ' ' </proc/${PPID}/cmdline 2>/dev/null | sed 's/ *$//')" \
    >"$AI_LIFECYCLE_LOCK_FILE" || true
}

ai_ensure_host_gateway() {
  local unit="$1"
  local url="$2"
  local label="$3"

  if systemctl is-active --quiet "$unit" \
    && curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
    echo "OK: $label already healthy"
    return 0
  fi

  systemctl restart "$unit" >/dev/null 2>&1 || true
  ai_wait_url "$url" "$label" 60
}

ai_active_heavy_profile() {
  ai_ensure_state_dir
  if [[ -f "$AI_ACTIVE_PROFILE_FILE" ]]; then
    cat "$AI_ACTIVE_PROFILE_FILE"
    return 0
  fi
  local p
  for p in "${HEAVY_PROFILES[@]}"; do
    if ai_compose ps --status running --services 2>/dev/null | grep -qx "llm-${p}"; then
      echo "$p"
      return 0
    fi
  done
  # legacy service name
  if ai_compose ps --status running --services 2>/dev/null | grep -qx "llm-general"; then
    echo "general"
    return 0
  fi
  echo ""
}

ai_set_active_heavy_profile() {
  ai_ensure_state_dir
  if [[ -z "${1:-}" ]]; then
    rm -f "$AI_ACTIVE_PROFILE_FILE"
  else
    printf '%s\n' "$1" >"$AI_ACTIVE_PROFILE_FILE"
  fi
}

ai_profile_service() {
  case "$1" in
    general) echo "llm-general" ;;
    coder) echo "llm-coder" ;;
    reasoning) echo "llm-reasoning" ;;
    vision) echo "llm-vision" ;;
    ornith) echo "llm-ornith" ;;
    reranker) echo "reranker" ;;
    *) return 1 ;;
  esac
}

ai_profile_port() {
  case "$1" in
    general) echo "8082" ;;
    coder) echo "8083" ;;
    reasoning) echo "8084" ;;
    vision) echo "8085" ;;
    ornith) echo "8086" ;;
    reranker) echo "8091" ;;
    *) return 1 ;;
  esac
}

ai_profile_alias() {
  case "$1" in
    general) echo "local-general" ;;
    coder) echo "local-coder" ;;
    reasoning) echo "local-reasoning" ;;
    vision) echo "local-vision" ;;
    ornith) echo "local-ornith" ;;
    reranker) echo "local-reranker" ;;
    *) return 1 ;;
  esac
}

ai_is_heavy_profile() {
  local p
  for p in "${HEAVY_PROFILES[@]}"; do
    [[ "$p" == "$1" ]] && return 0
  done
  return 1
}

ai_vram_free_mib() {
  nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ' || echo "0"
}

# Diagnostic-only cross-check: warns (does not change any decision) when the
# active-heavy marker says a heavy profile is loaded but the probed free VRAM
# is implausibly close to the full GPU total. See docs/TROUBLESHOOTING.md,
# "nvidia-smi VRAM free looks wrong after heavy container churn".
ai_vram_probe_warning() {
  local active="$1"
  local free_vram_mib="$2"
  [[ -n "$active" ]] || return 0
  PYTHONPATH="$AI_STATION_ROOT" python3 - "$active" "$free_vram_mib" <<'PY' 2>/dev/null || true
import sys
from apps.gateway.app.admission import load_hardware, vram_probe_looks_stale
active = sys.argv[1]
free_vram_mib = int(sys.argv[2]) if sys.argv[2].isdigit() else 0
warning = vram_probe_looks_stale(free_vram_mib, [active], load_hardware())
if warning:
    print(warning)
PY
}

ai_yaml_get_projects() {
  python3 - <<'PY'
from pathlib import Path
try:
    import yaml
except ImportError:
    # Minimal parser fallback: list project ids under projects:
    text = Path("/opt/ai-station/config/registry/projects.yaml").read_text(encoding="utf-8")
    print(text)
    raise SystemExit(0)
data = yaml.safe_load(Path("/opt/ai-station/config/registry/projects.yaml").read_text(encoding="utf-8")) or {}
for project in data.get("projects") or []:
    print(project.get("id", ""))
PY
}
