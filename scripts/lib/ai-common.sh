#!/usr/bin/env bash
# Shared helpers for AI Station platform CLI.
set -Eeuo pipefail

AI_STATION_ROOT="${AI_STATION_ROOT:-/opt/ai-station}"
AI_STATION_DATA="${AI_STATION_DATA:-/srv/ai-station}"
AI_STATE_DIR="${AI_STATE_DIR:-$AI_STATION_DATA/runtime}"
AI_ACTIVE_PROFILE_FILE="${AI_ACTIVE_PROFILE_FILE:-$AI_STATE_DIR/active-heavy-profile}"

HEAVY_PROFILES=(general coder reasoning vision)
OPTIONAL_PROFILES=(reranker)

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

ai_ensure_network() {
  if ! docker network inspect ai-platform >/dev/null 2>&1; then
    docker network create ai-platform >/dev/null
    echo "Created docker network: ai-platform"
  fi
}

ai_ensure_state_dir() {
  mkdir -p "$AI_STATE_DIR"
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
