# ADR-022: CPU Embedder Coexistence With One Heavy GPU Profile

- Status: Accepted
- Date: 2026-08-23

## Context

The 0.6B Qwen3 embedding server shared the GPU with the active heavy
llama.cpp chat profile (`gpus: all`, `-ngl 999`). On this 24 GiB
workstation the heavy profile already uses nearly all VRAM. The GPU
embedder then exited 0 after a CUDA error in
`ggml_backend_cuda_device_get_memory` during shutdown. Docker
`restart: unless-stopped` does not bring back a clean Exit 0, so
`:8090` stayed down and Open WebUI hybrid RAG had no embeddings.

The reranker is already CPU-only and starts with `ai start`. Embeddings
are a retrieval accessory, not the interactive generation core.

## Options considered

1. Keep the GPU embedder and rely on admission plus `restart: always`.
2. Stop the embedder whenever a heavy chat profile starts (RAG offline
   during chat).
3. Run the embedder on CPU (`gpus: []`, `-ngl 0`), like the reranker,
   so it coexists with one heavy GPU profile.
4. Replace llama.cpp embeddings with another engine.

## Evidence

- 2026-08-23 live state: `ai-station-embedder-1` Exit 0, `:8090` down,
  `ai health` failed, VRAM `22901 / 24463 MiB` with only `general`
  loaded. Log: CUDA unknown error in
  `ggml_backend_cuda_device_get_memory` after
  `operator(): cleaning up before exit`.
- Primary metric is **reliability of RAG while chat is loaded**, not
  embedding tok/s. A GPU embedder that dies fails that metric. CPU
  placement restores `/v1/models` beside the heavy profile.
- CPU embedding of a short English sentence on this host: **0.077 s**,
  1024-d vector, HTTP 200, while `general` occupied **22770 / 24463 MiB**
  VRAM (`benchmarks/results/20260823/embedder-cpu-smoke.json`).
  `ai health` exited 0. Community GPU-vs-CPU numbers are directional only.
- Option 4 would add a second embedding stack without a measured
  quality gap (ADR-003, ADR-005).

## Decision

Adopt option 3. The production embedder is CPU-only. Provider
`llama-cpp-embedder` uses `resource_group: cpu`, `minimum_vram_mib: 0`,
and no `nvidia_cuda` requirement. Starting ComfyUI still stops the
heavy llama.cpp chat profile; it no longer stops the embedder.

## Consequences

- RAG embeddings remain available while one heavy chat profile occupies
  the GPU.
- Embedding latency may be higher than a healthy GPU embedder. That is
  accepted: a slower live embedder beats a dead GPU embedder.
- The CUDA llama.cpp image is unchanged; CPU offload is `-ngl 0`.

## Risks

- CPU embedding under a large Knowledge ingest could contend with the
  host. Mitigation: existing Tika/Open WebUI batching; operators can
  pause ingest.
- Rollback to GPU is a Compose revert plus recreate, but it will
  likely die again next to a 35B Q4 profile on this GPU.

## Rollback

Restore `gpus: all` and `-ngl 999` on `embedder` in `compose.yml`,
restore `resource_group: gpu-light` in `config/providers.yaml`, then
`ai start` (or recreate `embedder`).

## Acceptance criteria

- `ai health` succeeds with one heavy profile **and** `:8090` up.
- Compose contract tests require `gpus: []` and `-ngl 0` on embedder.
- A dated CPU embedding smoke JSON exists under `benchmarks/results/`.
