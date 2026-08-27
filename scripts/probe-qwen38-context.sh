#!/usr/bin/env bash
# Probe Qwen3.8 general context on this GPU. Tries 262144 then 131072.
# Writes JSON under benchmarks/results/YYYYMMDD/. Does not print secrets.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
cd "$ROOT"
export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"
# shellcheck source=/dev/null
source "$ROOT/scripts/lib/ai-common.sh"

STAMP="$(date -u +%Y%m%d)"
OUT_DIR="${AI_STATION_SMOKE_OUT:-$ROOT/benchmarks/results/${STAMP}}"
mkdir -p "$OUT_DIR"
RESULT="$OUT_DIR/qwen38-context-probe.json"

gpu_csv() {
  nvidia-smi --query-gpu=memory.used,memory.free,memory.total --format=csv,noheader,nounits | head -1
}

wait_models() {
  local i
  for i in $(seq 1 90); do
    if curl -fsS --max-time 3 http://127.0.0.1:8082/v1/models >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}

try_context() {
  local ctx="$1"
  local kv="$2"
  echo "=== probe context=${ctx} kv=${kv} ==="
  local used_before free_before total
  IFS=',' read -r used_before free_before total <<<"$(gpu_csv | tr -d ' ')"

  LLM_GENERAL_CONTEXT="$ctx" \
  LLM_GENERAL_CACHE_TYPE_K="$kv" \
  LLM_GENERAL_CACHE_TYPE_V="$kv" \
    ai_compose --profile general up -d --force-recreate llm-general

  local start_ok=0
  if wait_models; then
    start_ok=1
  fi
  local used_after free_after
  IFS=',' read -r used_after free_after total <<<"$(gpu_csv | tr -d ' ')"
  local n_ctx=""
  if (( start_ok )); then
    n_ctx="$(curl -fsS --max-time 5 http://127.0.0.1:8082/props | python3 -c 'import sys,json; d=json.load(sys.stdin); print((d.get("default_generation_settings") or {}).get("n_ctx",""))')"
  fi
  local ingest_ok=0
  local ingest_err=""
  if (( start_ok )); then
    # ~ctx/4 spaces is a cheap length probe; llama.cpp counts tokens, not chars.
    python3 - "$ctx" <<'PY' >"$OUT_DIR/qwen38-ingest-tmp.json" || true
import json, os, sys, urllib.request
ctx = int(sys.argv[1])
# ~1 token per 4 chars for English filler; aim for ~min(ctx-256, 131072) tokens.
target = min(max(ctx - 512, 1024), 131072)
filler = ("Station loopback retrieval probe. " * ((target // 8) + 1))[: target * 4]
payload = json.dumps({
    "model": "ai-station-general",
    "messages": [{"role": "user", "content": filler + "\nReply with exactly: ctx-ok"}],
    "max_tokens": 8,
    "temperature": 0,
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8082/v1/chat/completions",
    data=payload,
    headers={"Content-Type": "application/json"},
)
out = {"ok": False}
try:
    with urllib.request.urlopen(req, timeout=1800) as resp:
        data = json.loads(resp.read().decode())
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    out = {
        "ok": "ctx-ok" in (msg.get("content") or ""),
        "usage": data.get("usage") or {},
        "preview": (msg.get("content") or "")[:80],
    }
except Exception as exc:
    out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
print(json.dumps(out))
PY
    ingest_ok="$(python3 -c "import json; print(int(json.load(open('$OUT_DIR/qwen38-ingest-tmp.json'))['ok']))")"
    ingest_err="$(python3 -c "import json; print(json.load(open('$OUT_DIR/qwen38-ingest-tmp.json')).get('error',''))")"
  fi
  python3 - <<PY
import json
from pathlib import Path
path = Path("$RESULT")
rows = json.loads(path.read_text()) if path.exists() else []
rows.append({
  "context": int("$ctx"),
  "kv": "$kv",
  "start_ok": bool($start_ok),
  "n_ctx": "$n_ctx",
  "vram_used_before_mib": int("$used_before" or 0),
  "vram_used_after_mib": int("$used_after" or 0),
  "vram_free_after_mib": int("$free_after" or 0),
  "vram_total_mib": int("$total" or 0),
  "ingest_ok": bool($ingest_ok),
  "ingest_error": """$ingest_err""",
})
path.write_text(json.dumps(rows, indent=2) + "\n")
print(json.dumps(rows[-1], indent=2))
PY
  (( start_ok )) && (( ingest_ok ))
}

: > /dev/null
python3 -c "from pathlib import Path; Path('$RESULT').write_text('[]\n')"

chosen=""
for kv in q8_0 q4_0; do
  if try_context 262144 "$kv"; then
    chosen="262144/$kv"
    break
  fi
done
if [[ -z "$chosen" ]]; then
  for ctx in 131072 65536 32768; do
    for kv in q8_0 q4_0; do
      if try_context "$ctx" "$kv"; then
        chosen="${ctx}/${kv}"
        break 2
      fi
    done
  done
fi

echo "CHOSEN=${chosen:-none}"
echo "Wrote $RESULT"
# Restore a known-good default if nothing ingested; leave the last successful
# (or last attempted) runtime up for the operator to inspect.
if [[ -z "$chosen" ]]; then
  echo "No 262144/131072 ingest succeeded; restoring 8192 q4_0."
  LLM_GENERAL_CONTEXT=8192 LLM_GENERAL_CACHE_TYPE_K=q4_0 LLM_GENERAL_CACHE_TYPE_V=q4_0 \
    ai_compose --profile general up -d --force-recreate llm-general
  wait_models || true
fi
