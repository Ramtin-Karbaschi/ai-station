# ADR-003: llama.cpp Permanent Roles

- Status: Accepted
- Date: 2026-07-23

## Context

Regardless of the Phase 3 interactive-engine decision, several workloads
depend on properties only llama.cpp provides in this environment.

## Options considered

1. Treat llama.cpp as fully replaceable.
2. Guarantee llama.cpp as production default or production fallback for
   defined workload classes.

## Evidence

- GGUF is the only artifact format covering all seven deployed model sets,
  including the vision model (mmproj) and 0.6B embedder/reranker.
- CPU/GPU layer offload (`-ngl`) is the only verified path for models
  larger than 24 GiB VRAM on this machine.
- The pinned container is integrated with installer, image lock, audit,
  and health tooling.

## Decision

llama.cpp remains: (a) production default for embeddings, reranking,
vision, and any larger-than-VRAM model; (b) production fallback for
interactive chat/coding even if SGLang is promoted; (c) the reference
implementation for the benchmark baseline.

## Consequences

Multi-engine documentation and admission policy must always account for a
llama.cpp fallback path; it is never uninstalled by an engine migration.

## Risks

- Blackwell CUDA-toolkit sensitivity (external reports of MMQ segfaults
  with CUDA 13 builds). Mitigation: pin known-good container digests and
  benchmark before each lock refresh.

## Rollback

Not applicable (this ADR preserves the incumbent).

## Acceptance criteria

- Registry marks llama.cpp providers as `fallback_provider` targets.
- Benchmark baseline exists before any competing engine is enabled.
