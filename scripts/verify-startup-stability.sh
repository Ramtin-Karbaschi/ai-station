#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

WINDOW_SEC="${1:-45}"
INTERVAL_SEC="${AI_STATION_VERIFY_INTERVAL_SEC:-5}"
fail=0
VERIFY_LOG="$(mktemp)"
trap 'rm -f -- "$VERIFY_LOG"' EXIT

if ! [[ "$WINDOW_SEC" =~ ^[0-9]+$ ]] || ! [[ "$INTERVAL_SEC" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_SEC" -le 0 ]]; then
  echo "Usage: $0 [window-seconds]" >&2
  exit 2
fi

snapshot_main_pid() {
  local unit="$1"
  systemctl show -p MainPID --value "$unit" 2>/dev/null | tr -d '[:space:]'
}

gateway_pid_initial="$(snapshot_main_pid ai-station-gateway.service)"
ui_gateway_pid_initial="$(snapshot_main_pid ai-station-ui-gateway.service)"

if [[ -z "$gateway_pid_initial" || "$gateway_pid_initial" == "0" ]]; then
  echo "FAIL: ai-station-gateway.service is not running"
  exit 1
fi

if [[ -z "$ui_gateway_pid_initial" || "$ui_gateway_pid_initial" == "0" ]]; then
  echo "FAIL: ai-station-ui-gateway.service is not running"
  exit 1
fi

echo "Watching startup stability for ${WINDOW_SEC}s..."
echo "Initial gateway PIDs: host=${gateway_pid_initial} ui=${ui_gateway_pid_initial}"

deadline=$((SECONDS + WINDOW_SEC))
attempt=0
while ((SECONDS < deadline)); do
  attempt=$((attempt + 1))

  if ! ./scripts/verify.sh >"$VERIFY_LOG" 2>&1; then
    cat "$VERIFY_LOG"
    fail=1
    break
  fi

  gateway_pid_now="$(snapshot_main_pid ai-station-gateway.service)"
  ui_gateway_pid_now="$(snapshot_main_pid ai-station-ui-gateway.service)"
  if [[ "$gateway_pid_now" != "$gateway_pid_initial" ]]; then
    echo "FAIL: ai-station-gateway.service restarted during stability window (${gateway_pid_initial} -> ${gateway_pid_now})"
    fail=1
    break
  fi
  if [[ "$ui_gateway_pid_now" != "$ui_gateway_pid_initial" ]]; then
    echo "FAIL: ai-station-ui-gateway.service restarted during stability window (${ui_gateway_pid_initial} -> ${ui_gateway_pid_now})"
    fail=1
    break
  fi

  echo "OK: stability check ${attempt} passed"
  sleep "$INTERVAL_SEC"
done

if ((fail)); then
  exit 1
fi

echo "OK: startup remained stable for ${WINDOW_SEC}s"
