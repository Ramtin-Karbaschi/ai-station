# Model Management

AI Station does not commit model binaries to Git.

The operator's remaining product choice is which local model fits this
machine's VRAM, RAM, and disk. Bytes live under `/srv/ai-station`.

The authoritative model definition is:

~~~text
config/model-manifest.json
~~~

Runtime catalog and provider lifecycle:

~~~text
config/model-catalog.json
config/providers.yaml
~~~

## Hardware guidance

On a single GPU, run **at most one** heavy profile at a time. These numbers
are planning hints, not guarantees:

| VRAM (approx.) | Start with |
|---|---|
| ≥ 22 GiB | Core `general` (Qwen3.6 35B-A3B Q4) plus embeddings |
| ≥ 18 GiB | `coder` (Qwen3 Coder 30B-A3B Q4) for OpenCode |
| ≥ 16 GiB | A smaller Q4 GGUF registered with `ai models add` |
| < 16 GiB | Do not expect the default 30–35B Q4 pack to fit |

Confirm with `nvidia-smi` and `ai provider start <id> --dry-run` before
downloading a multi-gigabyte file.

## Recommended models

Canonical bytes, SHA-256, and revisions live in
`config/model-manifest.json`. Sizes below are `size_bytes / 1024³`
(GiB, two decimals). Performance is from this workstation
(NVIDIA GeForce RTX 5090 Laptop, 24463 MiB VRAM) unless a dated
source is named. At most one heavy GPU profile runs at a time.

### Chat, vision, and retrieval

| Manifest id | Role | Size (GiB) | Measured performance (this GPU) |
|---|---|---:|---|
| `general-qwen3.6-35b-a3b-q4` | Default chat / tools | 20.61 | Dated llama.cpp bench 2026-07-23: ~3.4–4 decode tok/s at ~24 GiB VRAM. Production default. |
| `coder-qwen3-30b-a3b-q4` | OpenCode default | 16.45 | 2026-08-19 context smoke: 16384 ctx with q8 KV, ~20.7 GiB VRAM, short chat and tools passed. |
| `ornith-1.5-35b-q4` | Retained coding | 20.22 | 2026-08-23 LiteLLM `:4000`: identity 0.941 s, JSON 0.568 s, tools 0.893 s (pass). |
| `qwen38-27b-q4` | Retained dense VL + tools | 15.33 | 2026-08-23 LiteLLM `:4000`: identity 1.29 s, JSON 2.845 s (`max_tokens=256`, thinking on), tools 3.247 s (pass). |
| `qwen38-27b-mmproj-f16` | Qwen3.8 vision projector | 0.86 | Required with `qwen38-27b-q4`. Combined Qwen3.8 pack **16.19 GiB**. |
| `longwriter-zero-32b-q4` | Retained long-form writing | 18.49 | Q4_K_M chosen after Q8_0 failed (~2.7 tok/s). Selection smoke: 5.696 s / 22.47 tok/s. Checked-in 2026-08-23 JSON: 164.0 s / 0.78 tok/s under disk contention. |
| `reasoning-deepseek-r1-32b-q4` | Reasoning, no tools | 18.49 | High latency. 2026-08-20 short chat timed out at 180 s; not advertised for tools. |
| `vision-qwen3-vl-32b-q4` | Multimodal chat | 18.40 | Fits this ~24 GiB GPU with mmproj; no 2026-08-23 tok/s smoke. |
| `vision-qwen3-vl-32b-mmproj-q8` | Vision projector | 0.72 | Required with `vision-qwen3-vl-32b-q4`. Combined vision pack **19.12 GiB**. |
| `embedding-qwen3-0.6b-q8` | Retrieval embeddings | 0.60 | CPU/GPU embedder on `:8090`; started with `ai start`. |
| `reranker-qwen3-0.6b-q8` | Hybrid RAG rerank | 0.60 | CPU on `:8091`; started with `ai start`. |

### ComfyUI media (GPU-exclusive overlay)

These packs are retained production media. They are never experimental
and must never be deleted. Start with
`ai provider start comfyui-media-experimental` (historical command id).
That overlay stops the active llama.cpp heavy profile.

| Pack | Manifest ids | Size (GiB) | Measured wall-clock (2026-08-23) |
|---|---|---:|---|
| MiniMax Music 3 | `experimental-comfyui-music3-dit-int8`, `experimental-comfyui-music3-text-encoder-int8`, `experimental-comfyui-music3-vae` | 11.10 | Text-to-music 176.2 s |
| MiniMax H3 | `experimental-comfyui-h3-fl2va-int8`, `experimental-comfyui-h3-ref2va-int8`, `experimental-comfyui-h3-text-encoder-nvfp4`, `experimental-comfyui-h3-video-vae`, `experimental-comfyui-h3-audio-vae`, `experimental-comfyui-h3-fl2v-turbo-lora`, `experimental-comfyui-h3-ref2v-turbo-lora` | 62.73 | Text-to-video 302.3 s |
| FLUX.2-dev | `experimental-comfyui-flux2-dit-q4`, `experimental-comfyui-flux2-text-encoder-fp4`, `experimental-comfyui-flux2-vae` | 30.45 | Text-to-image 262.3 s |

### Pack totals (weights only)

| Pack | Size (GiB) |
|---|---:|
| Core (`general` + embedding) | 21.21 |
| Other chat/vision/rerank GGUFs | 54.66 |
| Retained chat (Ornith + Qwen3.8 + LongWriter) | 54.91 |
| ComfyUI MiniMax Music 3 | 11.10 |
| ComfyUI MiniMax H3 | 62.73 |
| ComfyUI FLUX.2-dev | 30.45 |
| **All manifest weights** | **235.05** |

Evidence files: `benchmarks/results/20260823/` (LiteLLM and ComfyUI
smokes). Hardware planning remains in the table above, not a guarantee
on other GPUs.

## Application size excluding model weights

Model GGUF and safetensors are **not** in Git. They live under
`/srv/ai-station/models`.

| What | Size | Notes |
|---|---|---|
| Git-tracked application (`git archive` / tracked files) | **~1.2 MiB** | Source, config, scripts, docs, tests, Compose files, ComfyUI workflow JSON. No weights. |
| Workstation checkout without `.git` or local Python virtualenvs | a few megabytes | Local caches and untracked files vary by machine. |
| Optional local Python virtualenvs (`.venvs/`) | not part of Git | Workstation-only; do not treat as product size. |
| Digest-pinned Compose images | tens of GiB | Runtime containers, not model weights and not the Git tree. |

The official project size **without AI model weights** is the Git
application: about **1.2 MiB** of tracked source. A full recommended
weight set is **235.05 GiB** under `/srv/ai-station` and is provisioned
separately with `ai models install` / `make models-core`.

## Manifest fields

Each model entry contains:

| Field | Meaning |
|---|---|
| `id` | Stable AI Station identifier |
| `role` | Operational role |
| `repo_id` | Hugging Face repository |
| `filename` | Exact upstream filename |
| `revision` | Immutable source commit |
| `destination` | Relative path beneath the data root |
| `size_bytes` | Expected file size |
| `sha256` | Expected SHA-256 checksum |
| `profiles` | Installation profiles containing the model |
| `operator_retained` | If true, `ai models remove` refuses with no override |

## Profiles

### Core

Default operational models:

- Qwen3.6 35B-A3B general (GGUF);
- Qwen3 Embedding 0.6B.

~~~bash
./scripts/provision-models.sh --profile core
./scripts/verify-models.sh --profile core
make models-core
~~~

### All

Core plus selectable heavy roles. These retained packs are never
experimental and must never be deleted: Ornith 1.5, Qwen3.8, LongWriter
Q4, and ComfyUI MiniMax Music 3 / MiniMax H3 / FLUX.2.

- Qwen3 Coder 30B-A3B;
- DeepSeek-R1 Distill Qwen 32B (reasoning);
- Qwen3-VL 32B + mmproj (vision);
- Ornith-1.5 35B Q4 (retained coding profile; does not replace coder);
- Qwen3.8 27B UD-Q4_K_M + mmproj (retained dense VL+tools; does not replace general or vision);
- LongWriter-Zero 32B Q4_K_M (retained long-form / RL writing; does not replace general);
- Qwen3 Reranker 0.6B (CPU; started with `ai start` for hybrid RAG).

~~~bash
./scripts/provision-models.sh --profile all
./scripts/verify-models.sh --profile all
~~~

ComfyUI MiniMax Music3 / H3 and FLUX.2-dev still-image packs are
**retained production media**, never experimental, and must never be
deleted. They live in profile `experimental-comfyui` (historical profile
name). They are GPU-exclusive and start through
`ai provider start comfyui-media-experimental`
(ADR-015, ADR-018, [clients/COMFYUI.md](clients/COMFYUI.md)).

## Day-to-day add and remove

~~~bash
ai models catalog
ai models catalog --json
ai models add coder-qwen3-30b-a3b-q4
ai models install coder-qwen3-30b-a3b-q4
ai models verify coder-qwen3-30b-a3b-q4
ai models remove coder-qwen3-30b-a3b-q4              # dry-run
ai models remove coder-qwen3-30b-a3b-q4 --confirm    # quarantine, not deletion
ai models restore coder-qwen3-30b-a3b-q4 --confirm
~~~

`ai models add <manifest-id>` installs a curated id. `remove` refuses the
active heavy profile. Required core models also require `--allow-required`.
Retained operator models (Ornith 1.5, Qwen3.8, LongWriter-Zero Q4, and
ComfyUI MiniMax Music 3 / MiniMax H3 / FLUX.2) cannot be removed or
quarantined. Quarantined files live under `/srv/ai-station/quarantine/models/`.

Windows Manager exposes Catalog, Install, Add, Remove, and Restore.

## Register a new Hugging Face GGUF

Do not use a mutable branch such as `main` as a production revision.

~~~bash
ai models add \
  --id my-model-q4 \
  --repo org/name \
  --filename model.gguf \
  --role general \
  --revision 0123456789abcdef0123456789abcdef01234567

# When size and sha256 are known:
ai models add ... --sha256 <64-hex> --size-bytes N --confirm
ai models install my-model-q4
~~~

A model is not a runtime profile until catalog, providers, and LiteLLM
routing are updated. The `add --confirm` command prints that next step.

## Resume behavior

The Hugging Face cache is retained at:

~~~text
/srv/ai-station/cache/huggingface
~~~

Interrupted downloads can resume from this cache.

`provision-models.sh` sets `HF_HUB_DOWNLOAD_TIMEOUT=600` and
`HF_HUB_ETAG_TIMEOUT=120` before importing `huggingface_hub` (upstream
defaults are 10 seconds and abort large files on a brief stall). Stale
`.lock` files for that repo are removed before each retry. Destination
files smaller than the manifest size are resumed with HTTP Range (aria2c
when present, otherwise curl) instead of being quarantined.

A downloaded file is placed at its final destination only after:

1. its size matches the manifest;
2. its SHA-256 checksum matches the manifest.

Full-size files with a mismatched checksum are quarantined rather than
silently overwritten.

## Default model paths

~~~text
/srv/ai-station/models/general
/srv/ai-station/models/coder
/srv/ai-station/models/ornith
/srv/ai-station/models/qwen38
/srv/ai-station/models/longwriter
/srv/ai-station/models/thinking
/srv/ai-station/models/vision
/srv/ai-station/models/embedding
/srv/ai-station/models/reranker
/srv/ai-station/models/whisper
/srv/ai-station/models/custom
/srv/ai-station/models/comfyui
~~~

## Runtime profile switch

~~~bash
ai models use general
ai models use coder
ai models use ornith
ai models use qwen38
ai models use longwriter
ai models stop
~~~

Admission dry-run:

~~~bash
ai provider start llama-cpp-coder --dry-run
ai provider start llama-cpp-ornith --dry-run
ai provider start llama-cpp-qwen38 --dry-run
ai provider start llama-cpp-longwriter --dry-run
~~~

`ornith`, `qwen38`, and `longwriter` remain optional heavy start
profiles (ADR-008, ADR-019, ADR-020). Their GGUF bytes are retained
operator models: never experimental and never deleted. Rollback of the
active GPU profile is `ai models use general`.
