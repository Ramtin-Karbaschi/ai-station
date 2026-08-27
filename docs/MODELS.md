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
| ≥ 22 GiB | Core `general` (Qwen3.8 27B Q4) plus embeddings |
| ≥ 18 GiB | `coder` (Ornith 1.5 35B-A3B Q4) for OpenCode |
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
| `qwen38-27b-q4` | Shared general / reasoning / vision base | 15.33 | 2026-08-23 LiteLLM `:4000`: identity 1.29 s, JSON 2.845 s (`max_tokens=256`, thinking on), tools 3.247 s (pass). |
| `ornith-1.5-35b-q4` | OpenCode default / agentic coding | 20.22 | 2026-08-23 LiteLLM `:4000`: identity 0.941 s, JSON 0.568 s, tools 0.893 s (pass). |
| `qwen38-27b-mmproj-f16` | Qwen3.8 vision projector | 0.86 | Required with `qwen38-27b-q4`. Combined Qwen3.8 pack **16.19 GiB**. |
| `longwriter-zero-32b-q4` | Retained long-form writing | 18.49 | Q4_K_M chosen after Q8_0 failed (~2.7 tok/s). Selection smoke: 5.696 s / 22.47 tok/s. Checked-in 2026-08-23 JSON: 164.0 s / 0.78 tok/s under disk contention. |
| `embedding-qwen3-8b-q4_k_m` | Retrieval embeddings | 4.36 | CPU on `:8090` (ADR-022); upgraded to Qwen3 8B Q4_K_M for stronger multilingual retrieval. |
| `reranker-qwen3-4b-q6_k` | Hybrid RAG rerank | 3.08 | CPU on `:8091`; official Qwen conversion via llama.cpp `4fc4ec55` then Q6_K (ADR-024). |
| `asr-qwen3-1.7b-q8` | Primary speech-to-text | 2.02 | ggml-org Q8_0; CPU profile `asr` on `:8092` (ADR-027). Weights installed; unified `/v1/audio/transcriptions` on the host gateway. |
| `asr-qwen3-1.7b-mmproj-q8` | Qwen3-ASR audio projector | 0.33 | Required with `asr-qwen3-1.7b-q8`. |

PaddleOCR-VL-1.6 sidecars (tokenizer, config, custom Python) live under
`models/ocr/paddleocr-vl-1.6/` as `ocr-paddleocr-vl-1.6-*` ids.

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

Studio 2026 additions are not production until a local smoke exists (ADR-028):

| Pack | Manifest ids | Size (GiB) | Status |
|---|---|---:|---|
| Z-Image-Turbo NVFP4 | `studio-z-image-turbo-nvfp4`, `studio-z-image-text-encoder-fp4`, `studio-z-image-vae` | 7.75 | Official Comfy-Org pin; DiT/TE/VAE on disk |
| Qwen-Image-Edit-2511 | `studio-qwen-image-edit-2511-fp8mixed` | 19.12 | Official Comfy-Org pin; download in progress |
| FLUX.2-klein-4B | `studio-flux2-klein-4b`, `studio-flux2-klein-text-encoder-fp4`, `studio-flux2-klein-vae` | 11.12 | Official Comfy-Org pin |
| Qwen-Image-2512 | `studio-qwen-image-2512-fp8`, `studio-qwen-image-text-encoder-nvfp4`, `studio-qwen-image-vae` | 24.96 | Official Comfy-Org pin |
| LTX-2.5 distilled NVFP4 | `studio-ltx25-distilled-nvfp4`, `studio-ltx25-text-encoder-int8`, `studio-ltx25-video-vae`, `studio-ltx25-audio-vae` | 33.43 | Official Lightricks pin (HF gated; this token can read it) |
| H3 ControlNet Union | `studio-h3-controlnet-union` | 6.34 | Official alibaba-pai pin |
| ACE-Step 1.5 | `studio-ace-step-1.5-turbo-aio`, `studio-ace-step-1.5-xl-sft`, `studio-ace-step-1.5-text-encoder-4b`, `studio-ace-step-1.5-vae` | 26.72 | Official Comfy-Org pin |
| InfiniteTalk | `studio-infinitetalk-single` | 2.53 | Official MeiGen ComfyUI pack |
| LatentSync 1.6 | `studio-latentsync-1.6-unet`, `studio-latentsync-1.6-syncnet` | 6.22 | Official ByteDance pin |
| SeedVR2-7B NVFP4 | `studio-seedvr2-7b-nvfp4`, `studio-seedvr2-vae` | 4.90 | Official Comfy-Org pin; 3B not kept |
| ThinkSound | `studio-thinksound`, `studio-thinksound-vae`, `studio-thinksound-synchformer` | 22.85 | Official FunAudioLLM pin |
| Fish Audio S2 Pro | `studio-fish-s2-pro-00001`, `studio-fish-s2-pro-00002`, `studio-fish-s2-pro-codec` | 10.23 | Official fishaudio pin; local/personal use; check LICENSE.md before any commercial use |
| Qwen3-TTS 1.7B | `studio-qwen3-tts-1.7b-customvoice`, `studio-qwen3-tts-1.7b-voicedesign`, `studio-qwen3-tts-tokenizer` | 7.77 | Official Qwen 12Hz CustomVoice + VoiceDesign |
| Hunyuan3D 2.1 | `studio-hunyuan3d-dit-fp16`, `studio-hunyuan3d-vae-fp16`, `studio-hunyuan3d-paint-unet`, `studio-hunyuan3d-image-encoder` | 12.31 | Official Tencent pin; isolated GPU-exclusive provider |
| PaddleOCR-VL-1.6 | `ocr-paddleocr-vl-1.6` plus sidecars `ocr-paddleocr-vl-1.6-tokenizer-json`, `ocr-paddleocr-vl-1.6-tokenizer-model`, `ocr-paddleocr-vl-1.6-config-json`, `ocr-paddleocr-vl-1.6-tokenizer-config-json`, `ocr-paddleocr-vl-1.6-special-tokens-map-json`, `ocr-paddleocr-vl-1.6-preprocessor-config-json`, `ocr-paddleocr-vl-1.6-processor-config-json`, `ocr-paddleocr-vl-1.6-generation-config-json`, `ocr-paddleocr-vl-1.6-added-tokens-json`, `ocr-paddleocr-vl-1.6-modeling-paddleocr-vl-py`, `ocr-paddleocr-vl-1.6-configuration-paddleocr-vl-py`, `ocr-paddleocr-vl-1.6-image-processing-paddleocr-vl-py`, `ocr-paddleocr-vl-1.6-processing-paddleocr-vl-py`, `ocr-paddleocr-vl-1.6-chat-template-jinja` | 1.80 | Official PaddlePaddle pin; Compose profile `ocr-vl` |

### Pack totals (weights only)

| Pack | Size (GiB) |
|---|---:|
| Core (`general` + embedding) | 15.93 |
| Other chat/vision/rerank GGUFs | 40.17 |
| Retained chat (Ornith + Qwen3.8 + LongWriter) | 54.91 |
| ComfyUI MiniMax Music 3 | 11.10 |
| ComfyUI MiniMax H3 | 62.73 |
| ComfyUI FLUX.2-dev | 30.45 |
| Speech (Qwen3-ASR 1.7B Q8 + mmproj) | 2.35 |
| Studio 2026 + OCR (pinned, not all accepted) | 198.10 |
| **All manifest weights** | **367.07** |

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

Current production-plus-studio manifest total after Qwen3.8/Ornith
consolidation plus pinned (not yet all locally accepted) studio/ASR/OCR
weights: **367.07 GiB**.

The official project size **without AI model weights** is the Git
application: about **1.2 MiB** of tracked source. The current manifest
weight set is **367.07 GiB** under `/srv/ai-station` and is provisioned
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

- Qwen3.8 27B shared general/reasoning GGUF;
- Qwen3 Embedding 8B Q4_K_M.

~~~bash
./scripts/provision-models.sh --profile core
./scripts/verify-models.sh --profile core
make models-core
~~~

### All

Core plus selectable heavy roles. These retained packs are never
experimental and must never be deleted: Ornith 1.5, Qwen3.8, LongWriter
Q4, and ComfyUI MiniMax Music 3 / MiniMax H3 / FLUX.2.

- Ornith-1.5 35B Q4 (default coding profile);
- Qwen3.8 27B UD-Q4_K_M + mmproj (shared general, reasoning, and vision profile);
- LongWriter-Zero 32B Q4_K_M (retained long-form / RL writing; does not replace general);
- Qwen3 Reranker 4B Q6_K (CPU; started with `ai start` for hybrid RAG).

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
/srv/ai-station/models/asr
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
