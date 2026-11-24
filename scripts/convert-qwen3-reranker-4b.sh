#!/usr/bin/env bash
# Convert official Qwen/Qwen3-Reranker-4B to Q6_K with the llama.cpp revision
# that matches the pinned server image (b9859 / 4fc4ec554).
set -Eeuo pipefail

DATA_ROOT="${AI_STATION_DATA:-/srv/ai-station}"
LLAMA_SRC="${LLAMA_SRC:-$DATA_ROOT/runtime/llama.cpp-4fc4ec55}"
LLAMA_REV="4fc4ec5541b243957ae5099edb67372f8f3b550e"
SRC_REPO="Qwen/Qwen3-Reranker-4B"
SRC_REV="22e683669bc0f0bd69640a1354a6d0aebcfeede5"
WORKDIR="$DATA_ROOT/cache/convert/qwen3-reranker-4b"
VENV="$DATA_ROOT/runtime/llama-convert-venv"
IMAGE="ghcr.io/ggml-org/llama.cpp@sha256:13f61752307fc4b96c8607a1bc03f977a2a27a4372d194f2aead83d60b964289"
DEST="$DATA_ROOT/models/reranker/qwen3-reranker-4b-q6_k.gguf"
F16="$WORKDIR/Qwen3-Reranker-4B-f16.gguf"
Q6="$WORKDIR/Qwen3-Reranker-4B-Q6_K.gguf"
HF_VENV="$DATA_ROOT/runtime/hf-provisioner-venv"

export DOCKER_CONTEXT="${DOCKER_CONTEXT:-default}"

if [[ ! -x "$LLAMA_SRC/convert_hf_to_gguf.py" ]]; then
  echo "ERROR: llama.cpp convert script missing at $LLAMA_SRC" >&2
  exit 1
fi
if [[ "$(git -C "$LLAMA_SRC" rev-parse HEAD)" != "$LLAMA_REV" ]]; then
  echo "ERROR: llama.cpp HEAD is not $LLAMA_REV" >&2
  exit 1
fi

mkdir -p "$WORKDIR/hf" "$(dirname "$DEST")"
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip
  "$VENV/bin/pip" install \
    -r "$LLAMA_SRC/requirements/requirements-convert_hf_to_gguf.txt"
fi

"$HF_VENV/bin/python" - "$SRC_REPO" "$SRC_REV" "$WORKDIR/hf" <<'PY'
import sys
from huggingface_hub import snapshot_download

snapshot_download(repo_id=sys.argv[1], revision=sys.argv[2], local_dir=sys.argv[3])
print("downloaded", sys.argv[1], sys.argv[2])
PY

if [[ ! -f "$F16" ]]; then
  "$VENV/bin/python" "$LLAMA_SRC/convert_hf_to_gguf.py" \
    --outtype f16 \
    --outfile "$F16" \
    "$WORKDIR/hf"
fi

if [[ ! -f "$Q6" ]]; then
  docker run --rm --entrypoint /app/llama \
    -v "$WORKDIR:/work" \
    "$IMAGE" \
    quantize "/work/Qwen3-Reranker-4B-f16.gguf" "/work/Qwen3-Reranker-4B-Q6_K.gguf" Q6_K
fi

python3 - "$Q6" "$DEST" "$WORKDIR" "$SRC_REPO" "$SRC_REV" "$LLAMA_REV" <<'PY'
import hashlib
import json
import os
import pathlib
import shutil
import sys
import time

q6 = pathlib.Path(sys.argv[1])
dest = pathlib.Path(sys.argv[2])
workdir = pathlib.Path(sys.argv[3])
digest = hashlib.sha256()
with q6.open("rb") as handle:
    while True:
        chunk = handle.read(16 * 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
sha = digest.hexdigest()
record = {
    "source_repo": sys.argv[4],
    "source_revision": sys.argv[5],
    "llama_cpp_revision": sys.argv[6],
    "quantization": "Q6_K",
    "size_bytes": q6.stat().st_size,
    "sha256": sha,
    "converted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "commands": [
        "python convert_hf_to_gguf.py --outtype f16 --outfile Qwen3-Reranker-4B-f16.gguf hf/",
        "llama quantize Qwen3-Reranker-4B-f16.gguf Qwen3-Reranker-4B-Q6_K.gguf Q6_K",
    ],
}
(workdir / "conversion-record.json").write_text(
    json.dumps(record, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(record, indent=2))
dest.parent.mkdir(parents=True, exist_ok=True)
tmp = dest.with_name(dest.name + ".partial")
shutil.copyfile(q6, tmp)
os.replace(tmp, dest)
print("installed", dest)
PY
