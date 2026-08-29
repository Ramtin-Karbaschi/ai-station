#!/usr/bin/env bash

AI_TOOL_GATEWAY_UNIT="ai-station-tool-gateway"
AI_TOOL_GATEWAY_URL="http://127.0.0.1:8892"
AI_TOOL_GATEWAY_ROOT="${AI_STATION_ROOT:-${ROOT:-/opt/ai-station}}"
AI_TOOL_GATEWAY_ASSET_DIR="${AI_STATION_TOOL_ASSET_ROOT:-/srv/ai-station/data/grounding/assets}"

ai_tools_healthy() {
  curl -fsS --max-time 3 "$AI_TOOL_GATEWAY_URL/healthz" >/dev/null 2>&1
}

ai_tools_system_unit_exists() {
  systemctl cat "${AI_TOOL_GATEWAY_UNIT}.service" >/dev/null 2>&1
}

ai_tools_user_unit_exists() {
  systemctl --user cat "${AI_TOOL_GATEWAY_UNIT}.service" >/dev/null 2>&1
}

ai_tools_install_system_unit() {
  local src="$AI_TOOL_GATEWAY_ROOT/infra/systemd/${AI_TOOL_GATEWAY_UNIT}.service"
  local dst="/etc/systemd/system/${AI_TOOL_GATEWAY_UNIT}.service"
  if [[ ! -f "$src" ]]; then
    echo "ERROR: missing unit file: $src" >&2
    return 1
  fi
  install -d -m 0755 "$AI_TOOL_GATEWAY_ASSET_DIR"
  install -m 0644 "$src" "$dst"
  systemctl daemon-reload
  systemctl enable "${AI_TOOL_GATEWAY_UNIT}.service" >/dev/null
}

ai_tools_start() {
  if ai_tools_healthy; then
    echo "OK: Tool Gateway already healthy"
    return 0
  fi
  if ai_tools_system_unit_exists; then
    ai_ensure_host_gateway "$AI_TOOL_GATEWAY_UNIT" "$AI_TOOL_GATEWAY_URL/healthz" "Tool Gateway"
    return
  fi
  # Control Panel runs `ai start` as root. A missing system unit must not fall
  # through to a user-manager restart (systemd exit 5 aborts the whole start).
  if [[ "$(id -u)" -eq 0 ]]; then
    echo "Installing ${AI_TOOL_GATEWAY_UNIT}.service (system unit was missing)..."
    ai_tools_install_system_unit
    ai_ensure_host_gateway "$AI_TOOL_GATEWAY_UNIT" "$AI_TOOL_GATEWAY_URL/healthz" "Tool Gateway"
    return
  fi
  if ai_tools_user_unit_exists; then
    systemctl --user restart "${AI_TOOL_GATEWAY_UNIT}.service"
    ai_wait_url "$AI_TOOL_GATEWAY_URL/healthz" "Tool Gateway" 60
    return
  fi
  echo "Installing user Tool Gateway unit..."
  "$AI_TOOL_GATEWAY_ROOT/scripts/install-tool-gateway-user.sh"
}

ai_tools_stop() {
  systemctl stop "$AI_TOOL_GATEWAY_UNIT" 2>/dev/null || true
  systemctl --user stop "${AI_TOOL_GATEWAY_UNIT}.service" 2>/dev/null || true
}

ai_tools_usage() {
  cat <<'EOF'
Usage: ai tools start|stop|status|smoke|capabilities
EOF
}

cmd_tools() {
  local sub="${1:-status}"
  case "$sub" in
    start)
      ai_tools_start
      ;;
    stop)
      ai_tools_stop
      ;;
    status)
      if ai_tools_system_unit_exists; then
        systemctl --no-pager --full status "$AI_TOOL_GATEWAY_UNIT" || true
      else
        systemctl --user --no-pager --full status "${AI_TOOL_GATEWAY_UNIT}.service" || true
      fi
      curl -fsS --max-time 5 "$AI_TOOL_GATEWAY_URL/healthz" | python3 -m json.tool
      ;;
    capabilities)
      curl -fsS --max-time 5 "$AI_TOOL_GATEWAY_URL/v1/capabilities" | python3 -m json.tool
      ;;
    smoke)
      curl -fsS --max-time 15 \
        -H 'Content-Type: application/json' \
        -d '{"query":"AI Station","limit":1}' \
        "$AI_TOOL_GATEWAY_URL/v1/search" | python3 -m json.tool
      ;;
    *)
      ai_tools_usage >&2
      return 2
      ;;
  esac
}
