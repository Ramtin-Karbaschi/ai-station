# ADR-028: Local AI Studio capability routing and GPU admission

- Status: Accepted
- Date: 2026-08-27

## Context

ComfyUI already hosts MiniMax Music 3, MiniMax H3, and FLUX.2-dev on a
GPU-exclusive overlay. The upgrade adds more media engines. Users should
pick capabilities (Image → Fast, Video → Draft), not raw model names.

## Decision

- Capability map: `config/studio/capabilities.yaml`.
- Shared ComfyUI core (`comfyui-media-experimental`) unless a workload
  cannot share that process (Hunyuan3D 2.1 is an isolated overlay).
- Admission: one heavy GPU workload. Starting ComfyUI or Hunyuan3D stops
  the active llama.cpp heavy profile, and the reverse.
- New engines arrive off-by-default with health, start/stop, workflow
  JSON, and a smoke path. `installed: false` until local acceptance.
- Prefer official publisher, then official GGUF, then Comfy-Org repack,
  then a trusted quant. Blackwell NVFP4 is preferred when official and
  verified on this RTX 5090 Laptop.

## Consequences

Do not enable Open WebUI image generation. Outputs stay under
`/srv/ai-station/runtime/comfyui/output` (or `ai output`). Do not mark a
capability production until a local smoke exists.
