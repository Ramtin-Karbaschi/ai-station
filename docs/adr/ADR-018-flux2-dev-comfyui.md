# ADR-018: FLUX.2-dev Still Images on the Experimental ComfyUI Overlay

- Status: Accepted (amended 2026-08-23)
- Date: 2026-08-22
- Extends [ADR-015](ADR-015-comfyui-minimax-media-studio.md)

## 2026-08-23 amendment

FLUX.2-dev still-image weights are retained production media with MiniMax
Music 3 / H3: never experimental and never deleted. Overlay filenames
stay historical. `--remove-weights` is refused.

## Context

The operator asked to add
[black-forest-labs/FLUX.2-dev](https://huggingface.co/black-forest-labs/FLUX.2-dev)
for local still-image generation. That checkpoint is a 32B rectified-flow
model under the FLUX Non-Commercial License, Hugging Face gated, and
BF16 weights will not fit a 24 GiB GPU.

AI Station already has an experimental ComfyUI overlay for MiniMax
Music 3 / H3 (ADR-015). Open WebUI `image_generation` stays off. A
second heavy image engine, a LiteLLM image API, or a remote Hugging Face
text encoder would violate the one-heavy-GPU and on-box rules.

## Options considered

1. Enable Open WebUI image generation against Automatic1111 / a new
   diffusers service.
2. Pin the official Comfy-Org `flux2_dev_fp8mixed.safetensors` pack
   (~35.4 GB DiT) plus the BF16 Mistral encoder (~35.6 GB).
3. Pin a 24 GiB-class conversion of the same BFL weights: city96
   `flux2-dev-Q4_K_M.gguf` (~20.1 GB) plus Comfy-Org FP4 mixed text
   encoder (~12.3 GB) and `flux2-vae.safetensors` (~321 MiB), loaded by
   a digest-pinned ComfyUI-GGUF custom node on the existing ComfyUI
   overlay.
4. Reject FLUX.2-dev on this GPU.

## Evidence

- Official Comfy-Org DiT `flux2_dev_fp8mixed.safetensors` is
  35 455 599 592 bytes. That exceeds this workstation's 24 463 MiB
  VRAM without unmeasured block-swap. It is not the 24 GiB default.
- BFL's consumer Diffusers example uses `diffusers/FLUX.2-dev-bnb-4bit`
  and a **remote** Hugging Face text encoder. Remote encode is off-box
  and is not a station default.
- city96 `FLUX.2-dev-gguf` is a direct GGUF conversion of
  `black-forest-labs/FLUX.2-dev` (same license terms). Q4_K_M is
  20 082 414 560 bytes at revision
  `ade5d688ddab0d9cf4a5b01bf4321e01c115020d`, SHA-256
  `fca680c7b221a713b5cf7db6cf6b33474875320ee61f4c585bc33fe391dab9a6`.
- Comfy-Org VAE and FP4 text encoder are ungated repacks of the same
  family, revision `ab9055628ea245000e610f2aa2c96f4746093546`.
- Pinned ComfyUI v0.33.3 (`4da9e2dbead52fc1e68beae33fe3d7ad63b63241`)
  already has `EmptyFlux2LatentImage`, `FluxGuidance`, and
  `CLIPLoader` type `flux2`. It does **not** load GGUF DiTs natively.
- ComfyUI-GGUF commit `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`
  (tarball SHA-256
  `688126d5c2b8c4ff061f56b23c3c6791ac01dc366e98d41ef1aaef374c36f283`)
  registers `.gguf` under `diffusion_models/`. License: Apache-2.0.
- H3 INT8 already streams ~21 GB DiT + encoder on this GPU (ADR-015
  smoke). Q4 DiT in the same size class is plausible; still-image
  quality/latency versus MiniMax is a different workload class, not a
  chat-engine replacement.
- Community 24 GB reports are directional only. First live image is a
  smoke, not a promotion.

## Decision

Adopt option 3.

- Classification: **retained production media** (amended 2026-08-23;
  originally experimental). Same overlay
  `compose.comfyui.experimental.yaml`, profile `comfyui-experimental`,
  provider `comfyui-media-experimental`, loopback `:8188`, GPU-exclusive
  and not started by `ai start`, mutually exclusive with llama.cpp.
- Workload class: still-image generation (FLUX.2-dev) on the existing
  media studio, beside MiniMax music/video. Not a second public API.
- Weights (manifest profile `experimental-comfyui`, not `core`/`all`):
  - `experimental-comfyui-flux2-dit-q4`
  - `experimental-comfyui-flux2-text-encoder-fp4`
  - `experimental-comfyui-flux2-vae`
- Text encoder loads with `CLIPLoader` `device=cpu` so the 24 GiB GPU
  holds the DiT. Default canvas size is 768×768, 20 steps.
- Pin ComfyUI-GGUF in `infra/comfyui/Dockerfile` (tarball + SHA-256).
  Do not bump ComfyUI past v0.33.3 in this ADR.
- Do **not** enable Open WebUI `image_generation`.
- Do **not** add a LiteLLM image route.
- Do **not** call the remote Hugging Face text encoder.
- Do **not** download the gated BF16 BFL tree.
- MiniMax remains the empty-canvas default. Queue Prompt may run the
  station FLUX.2 workflow as well as MiniMax graphs.
- Promotion to `optional_profile` requires a local smoke JSON under
  `benchmarks/results/` with no new critical reliability issue.

Operator path is unchanged from ADR-015, plus:

~~~bash
ai models install experimental-comfyui-flux2-dit-q4
ai models install experimental-comfyui-flux2-text-encoder-fp4
ai models install experimental-comfyui-flux2-vae
# UI: Workflows → flux2-text-to-image.json
~~~

Stop the overlay with `./scripts/uninstall-comfyui-experimental.sh`.
`--remove-weights` is refused.

## Consequences

Operators generate still images from ComfyUI on the same overlay as
MiniMax. Chat stays on LiteLLM `:4000`. Starting ComfyUI still stops
llama.cpp.

## Risks

- 24 GiB may still OOM at 1024² or with the text encoder on GPU.
  Mitigation: 768² default, CLIP on CPU, admission REJECT rather than
  optimistic START.
- GGUF conversion is not Comfy-Org native FP8. Quality is unknown
  locally. Mitigation: experimental; keep MiniMax workflows working.
- FLUX Non-Commercial License. Mitigation: record in the evaluation
  matrix; no commercial API wrapping.
- Unauthenticated ComfyUI. Mitigation: loopback only (ADR-015).

## Rollback

~~~bash
./scripts/uninstall-comfyui-experimental.sh
# --remove-weights is refused; FLUX.2 / MiniMax files stay on disk
ai models use coder
~~~

Leave overlay, ADR, manifest, and the GGUF node pin in Git.

## Acceptance criteria

1. `ai start` still does not start ComfyUI.
2. Open WebUI `ENABLE_IMAGE_GENERATION` remains `False`.
3. Manifest pins the three FLUX.2 files with immutable revision +
   SHA-256, outside `core`/`all`.
4. Dockerfile verifies the ComfyUI-GGUF tarball SHA-256.
5. `config/clients/comfyui/workflows/flux2-text-to-image.json` names
   those files and uses `UnetLoaderGGUF` / `EmptyFlux2LatentImage`.
6. A live 768² image is a separate smoke; this ADR does not claim it
   passed at merge time.
