#!/usr/bin/env bash
# Offline-safe health smoke for experimental ComfyUI. Optional --generate is live GPU work.
# Slim summaries go under benchmarks/results/; raw dumps stay in runtime (gitignored).
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${AI_STATION_SMOKE_OUT:-$ROOT/benchmarks/results/$(date -u +%Y%m%d)/comfyui}"
DUMP_DIR="${AI_STATION_SMOKE_DUMP:-${AI_STATION_DATA:-/srv/ai-station}/runtime/comfyui/smoke}"
HEALTH_URL="${COMFYUI_HEALTH_URL:-http://127.0.0.1:8188/system_stats}"
GENERATE=0
if [[ "${1:-}" == "--generate" ]]; then
  GENERATE=1
fi

mkdir -p "$OUT_DIR" "$DUMP_DIR"
stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if ! curl -fsS --max-time 10 "$HEALTH_URL" >"$DUMP_DIR/system_stats.json"; then
  python3 - "$OUT_DIR/health.json" "$stamp" "$HEALTH_URL" <<'PY'
import json, sys
path, stamp, url = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump(
    {
        "engine": "comfyui",
        "provider_id": "comfyui-media-experimental",
        "checked_at": stamp,
        "health_url": url,
        "ok": False,
        "error": "health endpoint unreachable",
    },
    open(path, "w", encoding="utf-8"),
    indent=2,
)
print()
PY
  echo "FAIL: ComfyUI health endpoint $HEALTH_URL"
  echo "Start it with: ai provider start comfyui-media-experimental"
  exit 1
fi

python3 - "$OUT_DIR/health.json" "$stamp" "$HEALTH_URL" <<'PY'
import json, sys
path, stamp, url = sys.argv[1], sys.argv[2], sys.argv[3]
json.dump(
    {
        "engine": "comfyui",
        "provider_id": "comfyui-media-experimental",
        "checked_at": stamp,
        "health_url": url,
        "ok": True,
        "generate": False,
    },
    open(path, "w", encoding="utf-8"),
    indent=2,
)
print()
PY
echo "OK: $HEALTH_URL"

if (( GENERATE == 0 )); then
  echo "Health-only smoke complete. Pass --generate to queue a short Music3 job."
  exit 0
fi

WORKFLOW="$ROOT/config/clients/comfyui/workflows/music3-text-to-music.json"
python3 - "$WORKFLOW" <<'PY' | curl -fsS --max-time 30 -H 'Content-Type: application/json' \
  --data-binary @- http://127.0.0.1:8188/prompt >"$DUMP_DIR/music3-prompt.json"
import json, sys
data = json.loads(open(sys.argv[1], encoding="utf-8").read())
json.dump({"prompt": data["prompt"]}, sys.stdout)
PY
echo "Queued Music3 prompt. Inspect $DUMP_DIR/music3-prompt.json and ComfyUI output/"
