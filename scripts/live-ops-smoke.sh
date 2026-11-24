#!/usr/bin/env bash
# Sequential operational smokes. One heavy GPU occupant at a time.
# Writes JSON under benchmarks/results/YYYYMMDD/. Does not print secrets.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/scripts/lib/ai-common.sh"

public_name_for_profile() {
  case "$1" in
    general) echo "Qwen3.8-27B-UD-Q4_K_M" ;;
    coder) echo "Ornith-1.5-35B-Q4_K_M" ;;
    reasoning) echo "Qwen3.8-27B-Reasoning-UD-Q4_K_M" ;;
    vision) echo "Qwen3.8-27B-Vision-UD-Q4_K_M" ;;
    ornith) echo "Ornith-1.5-35B-Q4_K_M" ;;
    qwen38) echo "Qwen3.8-27B-UD-Q4_K_M" ;;
    longwriter) echo "LongWriter-Zero-32B-Q4_K_M" ;;
    *) return 1 ;;
  esac
}

STAMP="$(date -u +%Y%m%d)"
OUT_DIR="${AI_STATION_SMOKE_OUT:-$ROOT/benchmarks/results/${STAMP}}"
mkdir -p "$OUT_DIR"
RESTORE_PROFILE="$(ai_active_heavy_profile || true)"
[[ -n "$RESTORE_PROFILE" ]] || RESTORE_PROFILE="general"
KEY="$(ai_master_key)"
[[ -n "$KEY" ]] || { echo "ERROR: LITELLM_MASTER_KEY missing" >&2; exit 2; }

chat_once() {
  local model="$1"
  local timeout="$2"
  local payload="$3"
  local dest="$4"
  local tmp code
  tmp="$(mktemp)"
  local start_ns
  start_ns="$(date +%s%N)"
  code="$(
    curl -sS -o "$tmp" -w "%{http_code}" --max-time "$timeout" \
      -H "Authorization: Bearer ${KEY}" \
      -H "Content-Type: application/json" \
      -d "$payload" \
      "http://127.0.0.1:4000/v1/chat/completions" || true
  )"
  python3 - "$tmp" "$code" "$start_ns" "$model" "$dest" <<'PY'
import json, sys, time
path, code, start_ns, model, dest = sys.argv[1:6]
raw = open(path, encoding="utf-8", errors="replace").read()
elapsed = (time.time_ns() - int(start_ns)) / 1e9
out = {"model": model, "http": int(code or 0), "elapsed_s": round(elapsed, 3), "pass": False}
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    out["error"] = raw[:400]
    open(dest, "w", encoding="utf-8").write(json.dumps(out, indent=2) + "\n")
    sys.exit(0)
choice = (data.get("choices") or [{}])[0]
msg = choice.get("message") or {}
content = msg.get("content") or ""
tools = msg.get("tool_calls") or []
out["finish_reason"] = choice.get("finish_reason")
out["content_preview"] = content[:200]
out["tool_names"] = [
    (t.get("function") or {}).get("name") for t in tools if isinstance(t, dict)
]
out["usage"] = data.get("usage") or {}
out["pass"] = int(code or 0) == 200 and (bool(str(content).strip()) or bool(tools))
if not out["pass"]:
    out["error"] = raw[:400]
open(dest, "w", encoding="utf-8").write(json.dumps(out, indent=2) + "\n")
PY
  rm -f "$tmp"
}

url_pass() {
  curl -fsS --max-time 5 "$1" >/dev/null 2>&1 && echo pass || echo fail
}

echo "=== Always-on / CPU probes ==="
python3 - "$OUT_DIR/tools-probes.json" \
  "$(url_pass http://127.0.0.1:3000)" \
  "$(url_pass http://127.0.0.1:3000/api/config)" \
  "$(url_pass http://127.0.0.1:4000/health/liveliness)" \
  "$(url_pass http://127.0.0.1:9998/tika)" \
  "$(curl -fsS --max-time 8 'http://127.0.0.1:8889/search?q=test&format=json' >/dev/null 2>&1 && echo pass || echo fail)" \
  "$(url_pass http://127.0.0.1:5678/healthz)" \
  "$(url_pass http://127.0.0.1:4096/global/health)" \
  "$("$ROOT/scripts/ai" graphify status >/dev/null 2>&1 && echo pass || echo fail)" \
  "$("$ROOT/scripts/ai" opencode doctor >/dev/null 2>&1 && echo pass || echo fail)" <<'PY'
import json, sys
path, webui, cfg, litellm, tika, searx, n8n, opencode, graphify, doctor = sys.argv[1:11]
json.dump(
    {
        "open_webui": webui,
        "open_webui_config": cfg,
        "litellm": litellm,
        "tika": tika,
        "searxng": searx,
        "n8n": n8n,
        "opencode_health": opencode,
        "graphify_status": graphify,
        "opencode_doctor": doctor,
    },
    open(path, "w", encoding="utf-8"),
    indent=2,
)
print("wrote", path)
PY

echo "=== Embedding ==="
python3 - "$OUT_DIR/embedder-cpu-smoke.json" <<'PY'
import json, sys, time, urllib.request
dest = sys.argv[1]
payload = json.dumps({"model": "ai-station-embedding", "input": "AI Station retrieval smoke"}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8090/v1/embeddings",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
t0 = time.perf_counter()
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode())
        vec = ((body.get("data") or [{}])[0].get("embedding")) or []
        out = {
            "engine": "llama.cpp",
            "placement": "cpu",
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "dim": len(vec),
            "http": resp.status,
            "pass": resp.status == 200 and len(vec) > 8,
        }
except Exception as exc:
    out = {"engine": "llama.cpp", "placement": "cpu", "pass": False, "error": str(exc)[:300]}
open(dest, "w", encoding="utf-8").write(json.dumps(out, indent=2) + "\n")
print(json.dumps(out))
PY

echo "=== Rerank ==="
python3 - "$OUT_DIR/reranker-cpu-smoke.json" <<'PY'
import json, sys, time, urllib.request
dest = sys.argv[1]
payload = json.dumps({
    "model": "ai-station-reranker",
    "query": "local RAG",
    "documents": ["hybrid BM25 plus vectors", "unrelated cooking recipe"],
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:8091/v1/rerank",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
t0 = time.perf_counter()
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read().decode())
        results = body.get("results") or body.get("data") or []
        out = {
            "elapsed_s": round(time.perf_counter() - t0, 3),
            "n_results": len(results) if isinstance(results, list) else 0,
            "http": resp.status,
            "pass": resp.status == 200,
            "body_keys": sorted(body.keys()),
        }
except Exception as exc:
    out = {"pass": False, "error": str(exc)[:300]}
open(dest, "w", encoding="utf-8").write(json.dumps(out, indent=2) + "\n")
print(json.dumps(out))
PY

timeout_for() {
  case "$1" in
    qwen38|longwriter) echo 180 ;;
    vision) echo 120 ;;
    reasoning) echo 300 ;;
    *) echo 90 ;;
  esac
}

for profile in general coder ornith qwen38 longwriter vision reasoning; do
  echo "=== Heavy profile ${profile} ==="
  dest="$OUT_DIR/${profile}-live-smoke.json"
  if ! "$ROOT/scripts/ai" models use "$profile"; then
    printf '%s\n' '{"pass": false, "error": "ai models use failed"}' >"$dest"
    continue
  fi
  model="$(public_name_for_profile "$profile")"
  timeout="$(timeout_for "$profile")"
  ping_payload="$(python3 -c 'import json,sys; print(json.dumps({"model":sys.argv[1],"messages":[{"role":"user","content":"Reply with the single token PONG."}],"max_tokens":16,"temperature":0}))' "$model")"
  chat_once "$model" "$timeout" "$ping_payload" "$OUT_DIR/${profile}-identity.json"
  tools_file=""
  case "$profile" in
    general|coder|ornith|qwen38)
      tools_payload="$(python3 -c 'import json,sys; print(json.dumps({"model":sys.argv[1],"messages":[{"role":"user","content":"Call get_time for timezone UTC."}],"tools":[{"type":"function","function":{"name":"get_time","description":"Return the current time","parameters":{"type":"object","properties":{"timezone":{"type":"string"}},"required":["timezone"]}}}],"max_tokens":64,"temperature":0}))' "$model")"
      chat_once "$model" "$timeout" "$tools_payload" "$OUT_DIR/${profile}-tools.json"
      tools_file="$OUT_DIR/${profile}-tools.json"
      ;;
  esac
  python3 - "$dest" "$OUT_DIR/${profile}-identity.json" "$tools_file" <<'PY'
import json, sys
dest, identity_path, tools_path = sys.argv[1], sys.argv[2], sys.argv[3]
identity = json.loads(open(identity_path, encoding="utf-8").read())
tools = None
if tools_path:
    tools = json.loads(open(tools_path, encoding="utf-8").read())
ok = bool(identity.get("pass"))
if tools is not None:
    ok = ok and bool(tools.get("pass"))
open(dest, "w", encoding="utf-8").write(json.dumps(
    {"identity": identity, "tools": tools, "pass": ok}, indent=2
) + "\n")
print(dest, "pass" if ok else "FAIL")
PY
done

echo "=== ComfyUI health (stops llama.cpp) ==="
comfy="fail"
if "$ROOT/scripts/ai" provider start comfyui-media-experimental; then
  if ai_wait_url "http://127.0.0.1:8188/system_stats" "ComfyUI" 180 \
    && "$ROOT/scripts/comfyui-media-smoke.sh"; then
    comfy="pass"
  fi
fi
python3 -c 'import json,sys; json.dump({"comfyui_health": sys.argv[1]}, open(sys.argv[2],"w"), indent=2)' "$comfy" "$OUT_DIR/comfyui-ops.json"
"$ROOT/scripts/ai" provider stop comfyui-media-experimental >/dev/null 2>&1 || true
echo "Restoring heavy profile ${RESTORE_PROFILE}"
"$ROOT/scripts/ai" models use "$RESTORE_PROFILE" || true

python3 - "$OUT_DIR" "$RESTORE_PROFILE" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
out_dir = Path(sys.argv[1])
restore = sys.argv[2]
tools = json.loads((out_dir / "tools-probes.json").read_text(encoding="utf-8"))
embed = json.loads((out_dir / "embedder-cpu-smoke.json").read_text(encoding="utf-8"))
rerank = json.loads((out_dir / "reranker-cpu-smoke.json").read_text(encoding="utf-8"))
comfy = json.loads((out_dir / "comfyui-ops.json").read_text(encoding="utf-8"))
profiles = {}
for name in ("general", "coder", "ornith", "qwen38", "longwriter", "vision", "reasoning"):
    path = out_dir / f"{name}-live-smoke.json"
    profiles[name] = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"pass": False}
required_tools = all(
    tools.get(k) == "pass" for k in ("open_webui", "open_webui_config", "litellm", "tika", "searxng")
) and embed.get("pass") and rerank.get("pass")
profile_ok = all(item.get("pass") for item in profiles.values())
summary = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "restore_profile": restore,
    "tools": {**tools, "embedding": embed, "reranker": rerank, **comfy},
    "profiles": profiles,
    "overall_required_pass": bool(required_tools and profile_ok),
    "overall_pass": bool(
        required_tools
        and profile_ok
        and tools.get("n8n") == "pass"
        and tools.get("opencode_health") == "pass"
        and tools.get("opencode_doctor") == "pass"
        and comfy.get("comfyui_health") == "pass"
    ),
}
(out_dir / "live-ops-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"wrote": str(out_dir / "live-ops-summary.json"), "overall_pass": summary["overall_pass"], "required": summary["overall_required_pass"]}))
sys.exit(0 if summary["overall_pass"] else 1)
PY
