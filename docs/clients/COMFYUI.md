# ComfyUI media studio on AI Station

ComfyUI is the retained **music, video, and still-image** UI next to
Open WebUI. It is never experimental and must never be deleted. Chat
stays on Open WebUI (`:3000`) and LiteLLM
(`http://127.0.0.1:4000/v1`). Media jobs use ComfyUI on
`http://127.0.0.1:8188`.

ADR: [ADR-015](../adr/ADR-015-comfyui-minimax-media-studio.md),
[ADR-018](../adr/ADR-018-flux2-dev-comfyui.md)

Open WebUI image generation stays off. Do not point applications at `:8188`.

## Why ComfyUI

MiniMax Music 3 and MiniMax H3 need native diffusion nodes. Open WebUI
cannot run those workflows. Official MiniMax SGLang serve for H3 wants
four GPUs; this workstation has one 24 GiB GPU. ComfyUI 0.33.3 loads the
official Comfy-Org quantized packs.

Local H3 is H3-Base 768p, 4–15 seconds, 24 fps, stereo audio. Hosted
H3-Context-IR and 2K regenerate APIs are not wired.

## Start and stop

At most one heavy GPU provider. Starting ComfyUI stops llama.cpp. The
CPU embedder (ADR-022) stays up.

~~~bash
ai models stop
ai provider start comfyui-media-experimental --dry-run
ai provider start comfyui-media-experimental
# browser: http://127.0.0.1:8188
ai provider stop comfyui-media-experimental
ai models use coder
~~~

Windows Manager: 39 start, 40 stop and restore coder, 41 open ComfyUI,
43 open the current media folder, 44 choose a media folder under
`/srv/ai-station/runtime`.

## Models

Weights live under `/srv/ai-station/models/comfyui/` and are listed in
`config/model-manifest.json` under profile `experimental-comfyui`
(historical name). They are retained operator models: never experimental
and never deleted. They are not part of `core` or `all`.

~~~bash
ai models install experimental-comfyui-music3-dit-int8
# …or provision the whole experimental-comfyui profile
./scripts/provision-models.sh --profile experimental-comfyui
~~~

Pinned workflows (INT8 / 24 GiB defaults) are in
`config/clients/comfyui/workflows/` and appear in the ComfyUI Workflows
list after start:

- `music3-text-to-music.json` — text to music, no extra files
- `h3-text-to-video.json` — text to video, no extra files (~3 s / 73 frames)
- `h3-image-to-video.json` — needs a first-frame image in Load Image
- `h3-reference-to-video.json` — needs a reference image in Load Image
- `flux2-text-to-image.json` — FLUX.2-dev Q4 GGUF still image, 768², CLIP on CPU
- `z-image-turbo-text-to-image.json` — Image → Fast (weights on disk; pending smoke)
- `flux2-klein-text-to-image.json` — Image → Interactive (weights on disk; pending smoke)
- `qwen-image-edit-2511.json` — Image → Edit (weights on disk; pending smoke)
- `qwen-image-2512-text-to-image.json` — Image → Graphic / Text (weights on disk; pending smoke)

Capability names (not raw model names) live in
`config/studio/capabilities.yaml` (ADR-028). LTX-2.5 NVFP4 weights are
size-matched on disk; pending ComfyUI smoke. Hunyuan3D 2.1 uses the
official Comfy-Org checkpoint on this same overlay.

The stock ComfyUI canvas is Flux.2 FP8, which this station does not ship
(35 GB DiT exceeds 24 GiB). On start, AI Station replaces that canvas
with MiniMax Music 3. Queue Prompt accepts MiniMax graphs and the
station FLUX.2 GGUF workflow. Other Flux/LTX/Wan templates still alert.

Still-image weights (city96 Q4 DiT of BFL FLUX.2-dev, Comfy-Org FP4
text encoder, Comfy-Org VAE) are extra `experimental-comfyui` manifest
ids. Official Comfy-Org FP8 mixed DiT is not the 24 GiB default
(ADR-018). FLUX weights are non-commercial.

You can also use Template Library: Audio → MiniMax Music 3;
Video → MiniMax H3. Keep the first Music3 clip around 15–20 seconds and
the first H3 clip around 4–5 seconds on this 24 GiB GPU.

If the NVFP4 H3 text encoder is unusable under WSL2, fall back to
`qwen3vl_32b_minimax_h3_int8_convrot.safetensors` (not in the default
manifest). See ADR-015.

## Health and smoke

~~~bash
curl -fsS http://127.0.0.1:8188/system_stats
./scripts/comfyui-media-smoke.sh
~~~

The smoke checks the health endpoint. `--generate` submits a short
Music3 request and is not part of `make check`. Slim JSON summaries
belong under `benchmarks/results/YYYYMMDD/comfyui/` (`health.json`,
`*-smoke.json`). Raw `/system_stats` and prompt dumps stay in
`/srv/ai-station/runtime/comfyui/smoke/` and are gitignored.

Local Music3 INT8 tiled-decode smoke on 2026-08-22 succeeded
(`benchmarks/results/20260822/comfyui/music3-smoke.json`). Browser
Music3 + H3 text-to-video also succeeded the same day
(`benchmarks/results/20260822/comfyui/browser-smoke.json`). That is not
a promotion to `optional_profile`.

## Output folder

Default host bind is `/srv/ai-station/runtime/comfyui/output/`.

~~~bash
ai output show
ai output set media /srv/ai-station/runtime/comfyui/output
~~~

Restart `comfyui-media-experimental` after changing `media` so the
bind mount moves. Windows Manager options 43–46 open or set folders.
See [ADR-016](../adr/ADR-016-operator-console-and-selectable-outputs.md).

## Stop the overlay

Stopping ComfyUI does **not** remove weights.

~~~bash
./scripts/uninstall-comfyui-experimental.sh
ai models use coder
~~~

`--remove-weights` is refused. MiniMax Music 3, MiniMax H3, and FLUX.2
must never be deleted.
