#!/usr/bin/env bash
# Bounded generation checks for the public LiteLLM API and direct startup probes.

ai_chat_completion_response_valid() {
  local allow_reasoning="${1:-false}"
  python3 -c '
import json
import sys

try:
    payload = json.loads(sys.stdin.read())
except (UnicodeDecodeError, json.JSONDecodeError):
    raise SystemExit(1)

choices = payload.get("choices") if isinstance(payload, dict) else None
if not isinstance(choices, list) or not choices:
    raise SystemExit(1)
message = choices[0].get("message") if isinstance(choices[0], dict) else None
if not isinstance(message, dict):
    raise SystemExit(1)
visible = message.get("content")
reasoning = message.get("reasoning_content")
has_visible = isinstance(visible, str) and bool(visible.strip())
has_reasoning = isinstance(reasoning, str) and bool(reasoning.strip())
if not has_visible and not (sys.argv[1] == "true" and has_reasoning):
    raise SystemExit(1)
' "$allow_reasoning"
}

# Probe a chat-completions endpoint without printing response bodies or putting
# the API key in curl's command line or a file. Set require_key=false and
# allow_reasoning=true only for the lock-owning llama.cpp startup probe.
ai_chat_generation_canary() {
  local endpoint="$1"
  local model="$2"
  local key="$3"
  local label="$4"
  local attempts="${5:-2}"
  local timeout="${6:-45}"
  local require_key="${7:-true}"
  local max_tokens="${8:-128}"
  local allow_reasoning="${9:-false}"
  local payload response_with_code response code attempt

  if [[ "$require_key" == true && -z "$key" ]]; then
    echo "FAIL: ${label} chat canary requires the LiteLLM master key" >&2
    return 1
  fi
  if [[ "$key" == *$'\n'* || "$key" == *$'\r'* ]]; then
    echo "FAIL: ${label} received an invalid multiline API key" >&2
    return 1
  fi
  if ! payload="$(python3 - "$model" "$max_tokens" <<'PY'
import json
import sys

payload = {
    "model": sys.argv[1],
    "messages": [{"role": "user", "content": "Reply with exactly OK. Do not include reasoning or explanation."}],
    "max_tokens": int(sys.argv[2]),
    "stream": False,
}
print(json.dumps(payload))
PY
  )"; then
    echo "FAIL: ${label} could not prepare the chat canary request" >&2
    return 1
  fi

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    if [[ -n "$key" ]]; then
      response_with_code="$(printf 'Authorization: Bearer %s\n' "$key" \
        | curl --silent --show-error --connect-timeout 5 --max-time "$timeout" \
          --write-out $'\n%{http_code}' --header @- \
          --header 'Content-Type: application/json' --data-binary "$payload" \
          "$endpoint" 2>/dev/null || true)"
    else
      response_with_code="$(curl --silent --show-error --connect-timeout 5 --max-time "$timeout" \
        --write-out $'\n%{http_code}' --header 'Content-Type: application/json' \
        --data-binary "$payload" "$endpoint" 2>/dev/null || true)"
    fi
    code="${response_with_code##*$'\n'}"
    response="${response_with_code%$'\n'*}"
    if [[ "$code" == 200 ]] && printf '%s' "$response" | ai_chat_completion_response_valid "$allow_reasoning"; then
      echo "OK: ${label} generated a non-empty chat completion"
      return 0
    fi
    echo "Chat canary ${label} attempt ${attempt}/${attempts} failed (HTTP ${code:-000}; empty or invalid completion is also a failure)" >&2
    (( attempt < attempts )) && sleep 1
  done

  echo "FAIL: ${label} chat generation is unavailable; check LiteLLM routing and the active model runtime" >&2
  return 1
}
