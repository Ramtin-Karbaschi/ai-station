# Output directory selection for AI Station (ADR-016).
# Sourced by scripts/ai.

ai_output_usage() {
  cat <<'EOF'
Usage:
  ai output show
  ai output set media|graphify|export PATH
  ai output open media|graphify|export
  ai output path media|graphify|export

media and graphify must stay under /srv/ai-station/runtime.
export may also be a Windows user folder via /mnt/<drive>/Users/...
Changing media requires restarting comfyui-media-experimental if it is up.
EOF
}

cmd_output() {
  local sub="${1:-}"
  shift || true
  case "$sub" in
    show|"") python3 "$ROOT/scripts/operator_output.py" show ;;
    path)
      local kind="${1:-}"
      [[ -n "$kind" ]] || { echo "Usage: ai output path media|graphify|export" >&2; exit 2; }
      python3 "$ROOT/scripts/operator_output.py" path "$kind"
      ;;
    set)
      local kind="${1:-}"
      local path="${2:-}"
      [[ -n "$kind" && -n "$path" ]] || {
        echo "Usage: ai output set media|graphify|export PATH" >&2
        exit 2
      }
      python3 "$ROOT/scripts/operator_output.py" set "$kind" "$path"
      ;;
    open)
      local kind="${1:-}"
      [[ -n "$kind" ]] || { echo "Usage: ai output open media|graphify|export" >&2; exit 2; }
      python3 "$ROOT/scripts/operator_output.py" path "$kind"
      ;;
    -h|--help|help)
      ai_output_usage
      ;;
    *)
      echo "Unknown output command: $sub" >&2
      ai_output_usage >&2
      exit 2
      ;;
  esac
}
