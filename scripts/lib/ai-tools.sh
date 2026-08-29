#!/usr/bin/env bash

AI_TOOL_GATEWAY_UNIT="ai-station-tool-gateway"
AI_TOOL_GATEWAY_URL="http://127.0.0.1:8892"

ai_tools_system_unit_exists() {
  systemctl cat "${AI_TOOL_GATEWAY_UNIT}.service" >/dev/null 2>&1
}

ai_tools_start() {
  if ai_tools_system_unit_exists; then
    ai_ensure_host_gateway "$AI_TOOL_GATEWAY_UNIT" "$AI_TOOL_GATEWAY_URL/healthz" "Tool Gateway"
    return
  fi
  systemctl --user restart "${AI_TOOL_GATEWAY_UNIT}.service"
  ai_wait_url "$AI_TOOL_GATEWAY_URL/healthz" "Tool Gateway" 60
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
