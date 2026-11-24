# SearXNG configuration and local-only secret maintenance.

cmd_searxng() {
  local group="${1:-}"
  shift || true
  if [[ "$group" != "secret" ]]; then
    echo "Usage: ai searxng secret status|provision" >&2
    return 2
  fi

  local action="${1:-status}"
  shift || true
  if [[ $# -gt 0 ]]; then
    echo "Usage: ai searxng secret status|provision" >&2
    return 2
  fi
  case "$action" in
    status|provision)
      python3 "$ROOT/scripts/lib/searxng_secret.py" "$action" --env-file "$ROOT/.env"
      ;;
    *)
      echo "Usage: ai searxng secret status|provision" >&2
      return 2
      ;;
  esac
}
