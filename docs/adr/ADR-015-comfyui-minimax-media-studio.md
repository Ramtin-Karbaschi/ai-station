# ADR-015: ComfyUI Experimental Media Studio for MiniMax Music3 and H3

- Status: Accepted (amended 2026-08-23)
- Date: 2026-08-22

## 2026-08-23 amendment

The operator classified MiniMax Music 3, MiniMax H3, and FLUX.2 as
**retained production media**: never experimental and never deleted.
Compose overlay/profile names stay historical (`experimental` in the
filename and `ai provider start` id). The overlay remains GPU-exclusive
and is not started by `ai start` because of the one-heavy-GPU rule, not
because the pack is disposable. `--remove-weights` is refused.

## Context

The operator wants local **music and video generation** using
[MiniMaxAI/MiniMax-Music3](https://huggingface.co/MiniMaxAI/MiniMax-Music3)
and [MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3)
beside Open WebUI chat.

Open WebUI remains the human chat/RAG client. Its
`ENABLE_IMAGE_GENERATION` / `image_generation` capability is off and
targets Automatic1111-style still images, not MiniMax H3 video+audio or
Music3 songs.

This workstation is a single RTX 5090 Laptop GPU (24 GiB, sm_120) under
WSL2. At most one heavy GPU provider may run (ADR-004). Official MiniMax
H3 SGLang serve uses `--num-gpus 4` and full BF16 weights are ~124 GB.
SGLang was already rejected for chat promotion after a 24 GiB OOM
(ADR-002).

## Options considered

1. Enable Open WebUI image generation and point it at MiniMax.
2. Serve MiniMaxAI original trees with SGLang-Omni / SGLang / diffusers
   as a second API next to LiteLLM.
3. Add an isolated, off-by-default ComfyUI Compose profile that loads
   the official Comfy-Org quantized packs (native H3 and Music3 nodes in
   ComfyUI >= 0.30.0), loopback-only, mutually exclusive with llama.cpp.

## Evidence

- MiniMax documents ComfyUI, SGLang, and diffusers. Native ComfyUI H3
  nodes landed in Comfy-Org/ComfyUI #15224 (v0.30.0). This station pins
  ComfyUI **v0.33.3** (`4da9e2dbead52fc1e68beae33fe3d7ad63b63241`).
- Comfy-Org packs, not the MiniMaxAI directory layout, are what ComfyUI
  loaders accept. Documented 24 GiB path: pruned INT8 ConvRot DiT plus a
  quantized Qwen3-VL-32B encoder and VAEs (~42 GB for FL2VA; +~20 GB for
  Ref2VA). Music3 INT8 pack is ~12 GB.
- Hardware profile: NVFP4 is unverified under WSL2 dxgkrnl. First pack
  still follows Comfy's NVFP4-AWQ encoder file; if that path is unusable,
  fall back to `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` with
  heavier CPU offload. That fallback is not assumed to work.
- H3-Context-IR and H3-Regenerate-2K are hosted MiniMax APIs. Wiring
  them would send prompts and media off-box. Local output is H3-Base
  768p, 4–15 s, 24 fps, stereo audio.

## Decision

Adopt option 3.

- Classification: **retained production media** (amended 2026-08-23;
  originally experimental). Isolated Compose overlay
  `compose.comfyui.experimental.yaml`, profile `comfyui-experimental`,
  provider `comfyui-media-experimental`. GPU-exclusive. Not started by
  `ai start`. Weights must never be deleted.
- Workload class: media generation. Does not replace llama.cpp, LiteLLM
  (`http://127.0.0.1:4000/v1`), or Open WebUI (`:3000`).
- Bind `127.0.0.1:8188` only. ComfyUI has no application auth; loopback
  is the access control.
- Weights: Comfy-Org files in `config/model-manifest.json` under profile
  `experimental-comfyui` (immutable revision + SHA-256). Not in `core`
  or `all`.
- Image: repository-controlled `infra/comfyui/Dockerfile` FROM a
  digest-pinned PyTorch CUDA 12.8 runtime (sm_120). Recorded in
  `config/dockerfile-base-lock.json`.
- Promotion to `optional_profile` requires a local smoke JSON under
  `benchmarks/results/` with no quality/reliability regression versus
  the documented 24 GiB pack. Vendor or community numbers are
  directional only.
- Reject SGLang-Omni and raw MiniMaxAI BF16 H3 on this GPU (4-GPU
  official serve; overlaps rejected chat SGLang).
- Do not enable Open WebUI `image_generation`.

Operator path:

~~~bash
ai models stop
ai provider start comfyui-media-experimental --dry-run
ai provider start comfyui-media-experimental
# UI: http://127.0.0.1:8188
ai provider stop comfyui-media-experimental
ai models use coder
~~~

Uninstall overlay (stops the container only):
`./scripts/uninstall-comfyui-experimental.sh`.
`--remove-weights` is refused; these files must never be deleted.

## Consequences

Operators keep chat on Open WebUI and open ComfyUI for MiniMax music
and video. Starting ComfyUI stops llama.cpp and the GPU embedder.
Chat is unavailable until a llama.cpp profile is restored.

## Risks

- 24 GiB sequential offload may OOM on H3. Mitigation: INT8 DiT, short
  clips (4 s), optional turbo LoRA, documented INT8 encoder fallback,
  admission REJECT rather than optimistic START.
- NVFP4 encoder may emulate slowly under WSL2. Mitigation: fallback
  file named in this ADR; do not claim NVFP4 tensor-core speed.
- Unauthenticated ComfyUI. Mitigation: loopback bind only; never LAN
  or wildcard publish.
- ComfyUI PyTorch wheels vs sm_120. Mitigation: CUDA 12.8 base known
  to include Blackwell; first live start is a smoke, not a promotion.

## Rollback

~~~bash
./scripts/uninstall-comfyui-experimental.sh
ai models use coder
~~~

Leave overlay, ADR, and manifest in Git. Weights stay under
`/srv/ai-station`; `--remove-weights` is refused.

## Acceptance criteria

1. `ai start` does not start ComfyUI.
2. Overlay publishes only `127.0.0.1:8188`.
3. Provider is `production_default` + `heavy` (`experimental: false`);
   admission against an active llama.cpp provider is
   `STOP_CONFLICTING_PROVIDER_AND_START`. Weights are `operator_retained`.
4. Manifest files use immutable revisions and SHA-256; profile is
   `experimental-comfyui` only.
5. Dockerfile `FROM` is digest-pinned and listed in the build lock.
6. Open WebUI `image_generation` stays false.
7. Unit/contract tests cover the overlay, provider, manifest, workflows,
   and Manager entries. Live generation is an operator smoke, not
   `make check`.
