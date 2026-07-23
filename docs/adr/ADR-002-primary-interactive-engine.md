# ADR-002: Primary Interactive Engine — Retain llama.cpp, Trial SGLang

- Status: Proposed
- Date: 2026-07-23

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
- No local benchmark exists yet for any engine; adoption without one would
  violate the benchmark-first rule.

## Decision

Retain llama.cpp as production default. Trial SGLang in Phase 2 as an
experimental, digest-pinned, localhost-only, off-by-default profile.
Reject vLLM for now (source-build cost duplicates SGLang's role).
Postpone TensorRT-LLM to Phase 6.

Promotion threshold (Phase 3): >= 20% improvement in decode tokens/s at
equal-or-better TTFT for the interactive chat workload, with no
structured-output or tool-calling regression, no new critical reliability
issue, and rollback verified. Quantization parity caveat: GGUF Q4_K_M vs
AWQ INT4 is close but not exact; the benchmark report must quantify
quality with the shared evaluation set before comparing speed.

## Consequences

- One new container and one new quantized artifact enter the manifest.
- Admission controller must treat SGLang as heavy (mutually exclusive).

## Risks

- Artifact availability for the exact incumbent model in AWQ/GPTQ form;
  if unavailable, the comparison model must change on both sides.

## Rollback

`docker compose --profile sglang-experimental down` plus removal of the
profile; no default path depends on it at any point.

## Acceptance criteria

- Benchmark JSON for both engines under `benchmarks/results/`.
- Decision recorded here with data, changing status to Accepted.
