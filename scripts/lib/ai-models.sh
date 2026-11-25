# Model storage and runtime profile commands for AI Station.
# Sourced by scripts/ai after shared helpers are available.

ai_models_usage() {
  cat <<'EOF'
Usage:
  ai models list
  ai models active
  ai models catalog [--json]
  ai models review [--json] [--before-replace ID] [--allow-experimental]
  ai models add --id ID --repo REPO --filename FILE --role ROLE --revision SHA \
      --sha256 HEX --size-bytes N [--destination REL] [--confirm]
  ai models add <manifest-id>
  ai models install|verify|remove|restore <manifest-id>
  ai models use <general|coder|reasoning|vision|ornith|qwen38|longwriter> [--dry-run]
  ai models stop
  ai models start-reranker|stop-reranker

add without --confirm is a dry-run. add <manifest-id> installs a curated id.
remove quarantines bytes; it does not delete them. Required models need
--allow-required. Retained operator models (Ornith 1.5, Qwen3.8,
LongWriter-Zero, ComfyUI MiniMax/FLUX.2) cannot be removed.
Stop the active heavy profile before removing its file.
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

ai_provider_id_for_profile() {
  local profile="${1:-}"
  [[ -n "$profile" ]] || return 1
  PYTHONPATH="$ROOT" python3 - "$profile" <<'PY'
import sys
from apps.gateway.app.admission import load_providers

profile = sys.argv[1]
for provider_id, provider in (load_providers().get("providers") or {}).items():
    if provider.get("heavy") and str(provider.get("profile") or "") == profile:
        print(provider.get("id") or provider_id)
        break
PY
}

ai_cpu_fallback_runtime_ready() {
  curl -fsS --max-time 5 http://127.0.0.1:8089/v1/models >/dev/null 2>&1
}

# Start the bounded CPU chat provider after the caller has classified the
# live WSL GPU as genuinely unavailable.  This path owns a lifecycle lock from
# ai start; prove the backend directly so it never calls the public :4000
# route while LiteLLM/host-gateway startup would wait on that same lock.
ai_start_cpu_fallback() {
  local provider_id="llama-cpp-general-cpu"
  local decision admission_status=0 service="llm-general-cpu"

  decision="$(PYTHONPATH="$ROOT" python3 -m apps.gateway.app.admission \
    "$provider_id" --context 2048 --json)" || admission_status=$?
  if (( admission_status != 0 )); then
    echo "$decision" >&2
    echo "ERROR: bounded CPU fallback admission rejected; no CPU runtime was started." >&2
    return "$admission_status"
  fi
  if ! printf '%s\n' "$decision" | PYTHONPATH="$ROOT" python3 -c '
import json, sys
decision = json.load(sys.stdin)
if decision.get("decision") != "START":
    raise SystemExit(
        "ERROR: bounded CPU fallback requires START admission; got "
        + str(decision.get("decision"))
    )
if decision.get("stop_providers"):
    raise SystemExit("ERROR: CPU fallback admission requested a provider stop")
'; then
    return 2
  fi

  local started_here=0
  if ! ai_cpu_fallback_runtime_ready; then
    ai_retry_compose --profile cpu-chat up -d "$service"
    started_here=1
    if ! ai_wait_url "http://127.0.0.1:8089/v1/models" "CPU chat runtime" 180; then
      ai_compose --profile cpu-chat stop "$service" >/dev/null 2>&1 || true
      return 1
    fi
  else
    echo "OK: CPU chat runtime already ready"
  fi

  if ! ai_chat_generation_canary \
    "http://127.0.0.1:8089/v1/chat/completions" \
    "ai-station-general-cpu" "" "direct CPU runtime warm-up" \
    2 90 false 8 false; then
    if (( started_here )); then
      ai_compose --profile cpu-chat stop "$service" >/dev/null 2>&1 || true
    fi
    return 1
  fi
  echo "CPU chat fallback ready (general/default only; GPU path remains preferred)."
}

cmd_models_review() {
  python3 "$ROOT/scripts/lib/catalog_review.py" "$@"
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
    echo "Usage: ai models use <general|coder|reasoning|vision|ornith|qwen38|longwriter> [--dry-run]" >&2
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

  # cmd_start already owns the lifecycle lock when it calls this function.
  # Direct model switches must share the lock with provider start/stop so a
  # media worker cannot race another profile transition.
  if [[ -z "${AI_LIFECYCLE_LOCK_FD:-}" ]]; then
    ai_lifecycle_lock "models-use-${profile}"
  fi
  current="$(ai_active_heavy_profile || true)"

  echo "Switching heavy model profile -> ${profile}"
  ai_stop_experimental_gpu_overlays
  if [[ "$current" == "comfyui-experimental" || "$current" == "ocr-vl" || "$current" == "sglang-experimental" ]]; then
    echo "Stopped GPU overlay: $current"
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
  # Publish only after readiness and warm-up succeed. The marker is the
  # operator-visible active state, not an intent signal; clear it explicitly
  # when startup fails so a partially started profile is never advertised.
  if ! ai_wait_url "http://127.0.0.1:${port}/v1/models" "Model $profile" 300; then
    ai_set_active_heavy_profile ""
    return 1
  fi
  if ! ai_litellm_warmup_chat "$profile"; then
    ai_set_active_heavy_profile ""
    return 1
  fi
  ai_set_active_heavy_profile "$profile"

  echo "Active model: $(public_name_for_profile "$profile") (profile=${profile}, port=${port})"
}

cmd_models_stop() {
  if [[ -z "${AI_LIFECYCLE_LOCK_FD:-}" ]]; then
    ai_lifecycle_lock "models-stop"
  fi
  local p
  # Check ComfyUI before stopping llama.cpp. If a media generation is in
  # flight, ai_stop_experimental_gpu_overlays rejects the transition and the
  # existing model service must remain available.
  ai_stop_experimental_gpu_overlays
  for p in "${HEAVY_PROFILES[@]}"; do
    ai_compose --profile "$p" stop "$(ai_profile_service "$p")" 2>/dev/null || true
  done
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
    review) cmd_models_review "$@" ;;
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
