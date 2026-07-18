#!/usr/bin/env bash
set -Eeuo pipefail

Q="/srv/ai-station/quarantine/duplicate-models-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$Q"

move_if_exists() {
  local src="$1"
  if [ -f "$src" ]; then
    mkdir -p "$Q/$(dirname "$src" | sed 's#^/srv/ai-station/models/##')"
    mv "$src" "$Q/$(dirname "$src" | sed 's#^/srv/ai-station/models/##')/"
    echo "Moved: $src"
  fi
}

# Keep the lowercase active paths used by .env.
move_if_exists "/srv/ai-station/models/thinking/DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf"
move_if_exists "/srv/ai-station/models/vision/qwen3-vl-32b-instruct/Qwen3VL-32B-Instruct-Q4_K_M.gguf"
move_if_exists "/srv/ai-station/models/vision/qwen3-vl-32b-instruct/mmproj-Qwen3VL-32B-Instruct-Q8_0.gguf"

echo
echo "Quarantine path:"
echo "$Q"

du -sh "$Q" || true
du -sh /srv/ai-station/models || true
