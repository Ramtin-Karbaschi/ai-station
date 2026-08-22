# Model storage and runtime profile commands for AI Station.
# Sourced by scripts/ai after shared helpers are available.

ai_models_usage() {
  cat <<'EOF'
Usage:
  ai models list
  ai models active
  ai models catalog [--json]
  ai models add --id ID --repo REPO --filename FILE --role ROLE --revision SHA \
      --sha256 HEX --size-bytes N [--destination REL] [--confirm]
  ai models add <manifest-id>
  ai models install|verify|remove|restore <manifest-id>
  ai models use <general|coder|reasoning|vision|ornith> [--dry-run]
  ai models stop
  ai models start-reranker|stop-reranker

add without --confirm is a dry-run. add <manifest-id> installs a curated id.
remove quarantines bytes; it does not delete them. Required models need
--allow-required. Stop the active heavy profile before removing its file.
EOF
}

cmd_models_list() {
  python3 - "$ROOT/config/registry/models.yaml" <<'PY'
from pathlib import Path
import sys
try:
    import yaml
except ImportError:
    yaml = None

path = Path(sys.argv[1])
if yaml is None:
    print(path.read_text(encoding="utf-8"))
else:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    print(f"{'PUBLIC_MODEL':<36} {'PROFILE':<12} {'PORT':<6} {'HEAVY':<6} {'STATUS'}")
    for alias, meta in (data.get("models") or {}).items():
        print(
            f"{str(meta.get('public_name','')):<36} {str(meta.get('profile','')):<12} "
            f"{str(meta.get('port','')):<6} {str(meta.get('heavy','')):<6} "
            f"{meta.get('status','')}"
        )
PY
}

cmd_models_catalog() {
  "$ROOT/scripts/model_manager.py" catalog "$@"
}

cmd_models_add() {
  if [[ $# -eq 1 && "$1" != --* ]]; then
    cmd_models_install "$1"
    return
  fi
  "$ROOT/scripts/model_manager.py" add "$@"
}

cmd_models_install() {
  local model_id="${1:-}"
  [[ -n "$model_id" ]] || { echo "Usage: ai models install <manifest-id>" >&2; exit 2; }
  shift || true
  "$ROOT/scripts/provision-models.sh" --id "$model_id" "$@"
}

cmd_models_verify() {
  local model_id="${1:-}"
  [[ -n "$model_id" ]] || { echo "Usage: ai models verify <manifest-id>" >&2; exit 2; }
  shift || true
  "$ROOT/scripts/verify-models.sh" --id "$model_id" "$@"
}

cmd_models_remove() {
  local model_id="${1:-}"
  [[ -n "$model_id" ]] || {
    echo "Usage: ai models remove <manifest-id> [--confirm] [--allow-required]" >&2
    exit 2
  }
  shift || true
  "$ROOT/scripts/model_manager.py" quarantine "$model_id" "$@"
}

cmd_models_restore() {
  local model_id="${1:-}"
  [[ -n "$model_id" ]] || {
    echo "Usage: ai models restore <manifest-id> [--confirm]" >&2
    exit 2
  }
  shift || true
  "$ROOT/scripts/model_manager.py" restore "$model_id" "$@"
}

cmd_models_active() {
  local active
  active="$(ai_active_heavy_profile || true)"
  if [[ -z "$active" ]]; then
    echo "No heavy model profile is active."
    return 0
  fi
  echo "profile: $active"
  echo "service: $(ai_profile_service "$active")"
  echo "model:   $(public_name_for_profile "$active")"
  echo "port:    $(ai_profile_port "$active")"
  echo "vram_free_mib: $(ai_vram_free_mib)"
}

cmd_models_use() {
  local profile="${1:-}"
  if [[ -z "$profile" ]] || ! ai_is_heavy_profile "$profile"; then
    echo "Usage: ai models use <general|coder|reasoning|vision|ornith> [--dry-run]" >&2
    exit 2
  fi
  shift

  local dry_run=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) dry_run=1; shift ;;
      *)
        echo "Unknown argument: $1" >&2
        exit 2
        ;;
    esac
  done

  local current service port other
  current="$(ai_active_heavy_profile || true)"
  service="$(ai_profile_service "$profile")"
  port="$(ai_profile_port "$profile")"

  if (( dry_run )); then
    echo "DRY RUN: ai models use ${profile}"
    echo "  current active profile: ${current:-(none)}"
    if [[ -n "$current" && "$current" != "$profile" ]]; then
      echo "  would stop previous profile: $current"
      echo "  would start: ${profile} (service=${service}, port=${port})"
    elif [[ "$current" == "$profile" ]]; then
      echo "  already active: no stop/start would be needed"
    else
      echo "  would start: ${profile} (service=${service}, port=${port})"
    fi
    echo "  target model: $(public_name_for_profile "$profile")"
    echo "No changes made (dry run)."
    return 0
  fi

  echo "Switching heavy model profile -> ${profile}"
  if [[ "$current" == "comfyui-experimental" || "$current" == "sglang-experimental" ]]; then
    # sglang-experimental is retired; still clear a stale profile name.
    echo "Stopping experimental overlay: $current"
    ai_stop_experimental_gpu_overlays
    ai_set_active_heavy_profile ""
    current=""
  fi
  if [[ -n "$current" && "$current" != "$profile" ]]; then
    echo "Stopping previous profile: $current"
    ai_compose --profile "$current" stop "$(ai_profile_service "$current")" || true
    local i free
    for ((i = 1; i <= 60; i++)); do
      free="$(ai_vram_free_mib)"
      if [[ "$free" =~ ^[0-9]+$ ]] && ((free >= 8000)); then
        echo "VRAM free: ${free} MiB"
        break
      fi
      sleep 2
    done
  fi

  for other in "${HEAVY_PROFILES[@]}"; do
    if [[ "$other" != "$profile" ]]; then
      ai_compose --profile "$other" stop "$(ai_profile_service "$other")" 2>/dev/null || true
    fi
  done

  ai_compose --profile "$profile" up -d "$service"
  ai_set_active_heavy_profile "$profile"
  ai_wait_url "http://127.0.0.1:${port}/v1/models" "Model $profile" 300
  ai_litellm_warmup_chat "$profile"

  echo "Active model: $(public_name_for_profile "$profile") (profile=${profile}, port=${port})"
}

cmd_models_stop() {
  local p
  for p in "${HEAVY_PROFILES[@]}"; do
    ai_compose --profile "$p" stop "$(ai_profile_service "$p")" 2>/dev/null || true
  done
  ai_stop_experimental_gpu_overlays
  ai_set_active_heavy_profile ""
  echo "All heavy model profiles stopped."
}

cmd_models_start_reranker() {
  ai_compose --profile reranker up -d reranker
  ai_wait_url "http://127.0.0.1:8091/v1/models" "Reranker" 120
}

cmd_models_stop_reranker() {
  ai_compose --profile reranker stop reranker 2>/dev/null || true
  echo "Reranker stopped."
}

cmd_models() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    list) cmd_models_list ;;
    list-active)
      cmd_models_list
      echo
      cmd_models_active
      ;;
    active) cmd_models_active ;;
    catalog) cmd_models_catalog "$@" ;;
    add) cmd_models_add "$@" ;;
    install) cmd_models_install "$@" ;;
    verify) cmd_models_verify "$@" ;;
    remove) cmd_models_remove "$@" ;;
    restore) cmd_models_restore "$@" ;;
    use) cmd_models_use "$@" ;;
    stop) cmd_models_stop ;;
    start-reranker) cmd_models_start_reranker ;;
    stop-reranker) cmd_models_stop_reranker ;;
    -h|--help|help|"") ai_models_usage ;;
    *)
      echo "Unknown models command: $sub" >&2
      ai_models_usage >&2
      exit 2
      ;;
  esac
}
