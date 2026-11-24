# ADR-028: Local AI Studio capability routing and GPU admission

- Status: Accepted
- Date: 2026-08-27

## Context

ComfyUI already hosts MiniMax Music 3, MiniMax H3, and FLUX.2-dev on a
GPU-exclusive overlay. The upgrade adds more media engines. Users should
pick capabilities (Image → Fast, Video → Draft), not raw model names.

## Decision

- Capability map: `config/studio/capabilities.yaml`.
- Shared ComfyUI core (`comfyui-media-experimental`) for media including
  Hunyuan3D 2.1 via the official Comfy-Org checkpoint
  `studio-hunyuan3d-2_1-comfy-checkpoint`. Do not invent a second
  unpinned Hunyuan container. `ai provider start hunyuan3d-2_1` starts
  the same ComfyUI overlay.
- Admission: one heavy GPU workload. Starting ComfyUI stops the active
  llama.cpp heavy profile, and the reverse.
- New engines arrive off-by-default. `installed: true` means the pinned
  weights size-match the manifest on this workstation.
  `configured_pending_smoke` means no local ComfyUI smoke yet.
  `production` requires that smoke. `installed: false` is unused now that
  LTX-2.5 NVFP4 size-matches on this workstation.
- Prefer official publisher, then official GGUF, then Comfy-Org repack,
  then a trusted quant. Blackwell NVFP4 is preferred when official and
  verified on this RTX 5090 Laptop.

## Consequences

Do not enable Open WebUI image generation. Outputs stay under
`/srv/ai-station/runtime/comfyui/output` (or `ai output`). Do not mark a
capability production until a local smoke exists.
