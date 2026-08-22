# ADR-002: Primary Interactive Engine — Retain llama.cpp; Reject SGLang Promotion

- Status: Accepted
- Date: 2026-07-23
- Updated: 2026-08-22

## Context

The default interactive backend is llama.cpp (pinned CUDA container,
build b9859). Candidates SGLang, vLLM, and TensorRT-LLM were researched
for RTX 5090 Laptop (sm_120) under WSL2 2.7.10
(see [TECHNOLOGY_EVALUATION_MATRIX.md](../research/TECHNOLOGY_EVALUATION_MATRIX.md)).

## Options considered

1. Retain llama.cpp only.
2. Trial SGLang as an isolated experimental provider (v0.5.13+ has
   official SM120 support; OpenAI-compatible; Prometheus metrics; RadixAttention
   prefix caching; continuous batching; xgrammar structured output).
3. Trial vLLM (requires source build for consumer SM120 — official wheels
   exclude it; higher reproducibility cost).
4. Adopt TensorRT-LLM now (per-model engine builds; NVFP4/FP8 under WSL2
   dxgkrnl not verified; highest operational cost).

## Evidence

- SGLang release notes list SM120 support merged upstream; container
  distribution allows digest pinning; WSL2 >= 2.7.0 provides CUDA graph
  capture on Blackwell (community-verified, WSL issue #14452).
- FP8 under WSL2 falls back to slow emulated paths (community benchmarks),
  so the trial must use AWQ/GPTQ Marlin INT4 artifacts.
- Phase 1 llama.cpp baseline exists at
  `benchmarks/results/20260723/llama-cpp/general-qwen3.6.json`.
- Phase 2/3 SGLang trial (2026-07-24):
  - Image: `lmsysorg/sglang@sha256:920df39109c60429b0a23eaacfd2786fcf1595c12f3ca4fc6e153b2abe34865f`
  - Weights: `cyankiwi/Qwen3.6-35B-A3B-AWQ-4bit@00fcea2d3bcf5389b518d4fc082e5590e0ba4844` (SHA-256 verified)
  - Result: **failed to serve** on 24 GiB VRAM. Weight load alone ~22.5 GiB;
    hybrid mamba/linear-attention state cache then required ~5 GiB more
    headroom. CPU offload (`--cpu-offload-gb 6`) hit a cuda/cpu device
    mismatch under AWQ Marlin.
  - Evidence file:
    `benchmarks/results/20260724/sglang/general-qwen3.6-awq-oom.json`

## Decision

Retain llama.cpp as the production primary interactive engine.

**Reject SGLang promotion** on this workstation for the incumbent
Qwen3.6-35B-A3B MoE family: no healthy OpenAI endpoint could be stood up,
so the >= 20% decode/TTFT promotion threshold cannot be evaluated and is
not met.

On 2026-08-22 the unused experimental Compose overlay, provider entry,
uninstall script, and AWQ shard pins were removed from the live tree.
They were not serving requests and could not be started on this GPU.
The OOM evidence JSON remains under `benchmarks/results/20260724/sglang/`.
SGLang is not an optional production path.

Continue to postpone vLLM (source-build cost) and TensorRT-LLM (Phase 6).

## Consequences

- Production default unchanged.
- No SGLang provider, Compose overlay, or start command remains in the
  live tree. Persian/English OCR stays on Tika + Tesseract (`fas`), not
  on a second GPU engine.
- Revisit only if a same-family artifact loads with usable KV headroom on
  this GPU, or hardware VRAM increases. Any reopen requires a new ADR
  plus a new isolated overlay; do not restore the deleted files by habit.

## Risks

- Future denser AWQ/GPTQ builds or SGLang memory improvements could reopen
  the comparison; any reopen requires a new benchmark JSON and ADR update.

## Rollback

The 2026-07-24 trial already rolled back to llama.cpp. Overlay removal is
reversed only from Git history after a new ADR; do not reactivate the
rejected 24 GiB AWQ serve path.

## Acceptance criteria

- Benchmark JSON for both engines under `benchmarks/results/` — met via
  llama.cpp success JSON plus SGLang failure JSON with explicit OOM cause.
- Decision recorded here with data — met (Accepted).
