# Wave 0 operational commands. Sourced by scripts/ai.

ai_ops_python() {
  python3 "$@"
}

cmd_restore() {
  local flag="${1:-}"
  if [[ "$flag" != "--dry-run" ]]; then
    echo "ERROR: live restore is not implemented." >&2
    echo "Verify a backup with: ai restore --dry-run [--id YYYYMMDD-HHMMSS]" >&2
    echo "Production restore still needs an explicit operator procedure." >&2
    exit 2
  fi
  shift || true
  ai_ops_python "$ROOT/scripts/lib/restore_dry_run.py" --dry-run "$@"
}

cmd_retention() {
  local sub="${1:-status}"
  shift || true
  case "$sub" in
    status|enable|disable|apply)
      ai_ops_python "$ROOT/scripts/lib/retention.py" "$sub" "$@"
      ;;
    -h|--help|help)
      cat <<'EOF'
Usage:
  ai retention status
  ai retention enable [--ttl-days 90]
  ai retention disable
  ai retention apply [--dry-run]

Off until enable. Default TTL is 90 days once enabled.
apply --dry-run counts rows; apply deletes. Logs counts, not content.
EOF
      ;;
    *)
      echo "Unknown retention command: $sub" >&2
      echo "Usage: ai retention status|enable|disable|apply" >&2
      exit 2
      ;;
  esac
}

cmd_alerts() {
  case "${1:-}" in
    -h|--help|help)
      cat <<'EOF'
Usage:
  ai alerts [--dry-run] [--json]
  ai alerts summary

Soft usage alerts (about 3x recent daily mean) and lean health alerts
(disk 85%, CUDA OOM, always-on container down). Never rejects requests.
Alert files are size-capped (256 KiB) and dropped after 72 hours.
EOF
      return 0
      ;;
  esac
  ai_ops_python "$ROOT/scripts/lib/station_alerts.py" "$@"
}

cmd_sso() {
  local sub="${1:-status}"
  shift || true
    case "$sub" in
    status|configure|disable|probe)
      ai_ops_python "$ROOT/scripts/lib/sso.py" "$sub" "$@"
      ;;
    -h|--help|help)
      cat <<'EOF'
Usage:
  ai sso status
  ai sso configure --issuer URL --client-id ID [--secret-file PATH] [--dry-run]
  ai sso probe --issuer URL [--dry-run]
  ai sso disable [--dry-run]

OIDC is the only supported human identity path (ADR-030). LDAP is not
supported. Local signup stays off. Break-glass operator login stays on
the Open WebUI form. Live configure refuses if Open WebUI has no local
operator. LiteLLM project keys are unchanged.
EOF
      ;;
    *)
      echo "Unknown sso command: $sub" >&2
      echo "Usage: ai sso status|configure|probe|disable" >&2
      exit 2
      ;;
  esac
}

cmd_hardware() {
  local sub="${1:-detect}"
  shift || true
  case "$sub" in
    detect|status|-h|--help|help|"")
      if [[ "$sub" == "-h" || "$sub" == "--help" || "$sub" == "help" ]]; then
        cat <<'EOF'
Usage:
  ai hardware detect [--dry-run]

Print GPU count, gpu_index placement facts, and NPU presence.
Does not enable NPU offload or change the CPU embed/rerank/ASR path.
EOF
        return 0
      fi
      PYTHONPATH="$ROOT" python3 "$ROOT/scripts/lib/hardware_detect.py" detect "$@"
      ;;
    *)
      echo "Unknown hardware command: $sub" >&2
      echo "Usage: ai hardware detect" >&2
      exit 2
      ;;
  esac
}

cmd_media() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    guard|audit)
      ai_ops_python "$ROOT/scripts/lib/media_guard.py" "$sub" "$@"
      ;;
    -h|--help|help|"")
      cat <<'EOF'
Usage:
  ai media guard --file WORKFLOW.json [--dry-run]
  ai media audit [--limit N]

Hash ComfyUI prompts, deny disallowed media requests, and write a
size-capped audit log. Raw prompt text is never stored.
EOF
      ;;
    *)
      echo "Unknown media command: $sub" >&2
      echo "Usage: ai media guard|audit" >&2
      exit 2
      ;;
  esac
}

cmd_roi() {
  case "${1:-}" in
    -h|--help|help)
      cat <<'EOF'
Usage:
  ai roi [--days N] [--tariff PATH] [--dry-run] [--json]

Compare LiteLLM spend to an operator-supplied cloud tariff JSON.
Never rejects inference requests.
EOF
      return 0
      ;;
  esac
  ai_ops_python "$ROOT/scripts/lib/roi.py" "$@"
}

cmd_lora() {
  local sub="${1:-status}"
  shift || true
  case "$sub" in
    status|validate|plan|train|register|apply|disable)
      ai_ops_python "$ROOT/scripts/lib/lora.py" "$sub" "$@"
      ;;
    -h|--help|help)
      cat <<'EOF'
Usage:
  ai lora status
  ai lora validate [--dataset PATH]
  ai lora plan [--dataset PATH] [--base qwen38-27b-q4] [--id NAME]
  ai lora train   # exits 2; training is off-box
  ai lora register --adapter FILE.gguf --id NAME [--base ID] [--dry-run]
  ai lora apply --id NAME [--dry-run]
  ai lora disable [--dry-run]

Optional GGUF LoRA on llama.cpp (--lora). No new training engine.
EOF
      ;;
    *)
      echo "Unknown lora command: $sub" >&2
      echo "Usage: ai lora status|validate|plan|train|register|apply|disable" >&2
      exit 2
      ;;
  esac
}

cmd_tenants() {
  local sub="${1:-status}"
  shift || true
  case "$sub" in
    status|list|create|show|disable|doctor)
      ai_ops_python "$ROOT/scripts/lib/tenants.py" "$sub" "$@"
      ;;
    -h|--help|help)
      cat <<'EOF'
Usage:
  ai tenants status|list|doctor
  ai tenants create ID [--models M1,M2] [--dry-run]
  ai tenants show ID
  ai tenants disable ID [--dry-run]

Logical isolation: one LiteLLM project key per tenant (ADR-036).
Does not partition Open WebUI chat storage.
EOF
      ;;
    *)
      echo "Unknown tenants command: $sub" >&2
      echo "Usage: ai tenants status|list|create|show|disable|doctor" >&2
      exit 2
      ;;
  esac
}

cmd_voice() {
  case "${1:-}" in
    setup)
      [[ $# -eq 1 ]] || { echo "Usage: ai voice setup" >&2; return 2; }
      ai_ops_python "$ROOT/apps/voice/provision.py" --data-root "$AI_STATION_DATA"
      ai_compose --profile voice up -d --build station-voice
      return
      ;;
    -h|--help|help)
      cat <<'EOF'
Usage:
  ai voice setup
  ai voice status [--no-probe]
  ai voice smoke [--dry-run] [--write PATH]
  ai voice turn --dry-run [--transcript TEXT]
  ai voice turn --transcript TEXT
  ai voice turn --file AUDIO

Open WebUI Voice Mode uses the station's local audio routes through LiteLLM.
The operator CLI also provides one-turn diagnostics and Qwen3-TTS weight verification.
EOF
      return 0
      ;;
  esac
  ai_ops_python "$ROOT/scripts/lib/voice.py" "$@"
}

ai_start_voice_if_provisioned() {
  local models="${AI_STATION_DATA}/models/voice/piper"
  [[ -s "$models/en.onnx" && -s "$models/en.onnx.json" ]] || return 0
  [[ -s "$models/fa.onnx" && -s "$models/fa.onnx.json" ]] || return 0
  if ! ai_compose --profile voice up -d station-voice; then
    echo "WARNING: Local voice backend failed to start." >&2
  fi
}
