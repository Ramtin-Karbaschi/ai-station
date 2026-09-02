# ADR-032: Optional NPU Offload for CPU-Class Workloads

- Status: Accepted
- Date: 2026-09-02
- Relates: [ADR-022](ADR-022-cpu-embedder-coexistence.md),
  [ADR-027](ADR-027-asr-primary-fallback.md)

## Context

Embedding, rerank, and ASR run on CPU so they coexist with one heavy
GPU profile (ADR-022, ADR-027). Some customer hosts, including this
one (Intel Core Ultra 9 275HX / Intel AI Boost), have an NPU.
`config/hardware-profile.json` does not record it. The product must
use that capacity when a backend is verified. Heavy LLM inference
stays on GPU.

Candidate NPU backends and speedups are **unknown** until measured.
Do not guess tok/s or quality.

## Options considered

1. Ignore NPU.
2. Move the heavy LLM onto NPU.
3. Detect NPU in the hardware profile. Keep GPU for heavy chat,
   vision, and ComfyUI. Allow an optional provider profile that
   places embed / rerank / ASR on NPU after a local apples-to-apples
   benchmark versus the current CPU path. If no NPU or the benchmark
   fails the 20% promotion rule, keep CPU.

## Evidence

- CPU embedder smoke on this host: 0.077 s for a short sentence
  while general occupied VRAM
  (`benchmarks/results/20260823/embedder-cpu-smoke.json`).
- NPU throughput, llama.cpp/OpenVINO/other backend fitness, and
  WSL2 exposure are not measured here.

## Decision

Adopt option 3. Classification: optional profile, off by default,
localhost only, with health checks and an uninstall path once
implemented.

## Consequences

- Wave 2 adds NPU fields to the hardware snapshot and a detect
  command.
- Promotion requires `benchmarks/results/` and an ADR or an update
  to this one with numbers.
- ADR-022 CPU coexistence remains the production default until
  that evidence exists.

## Risks

- A slow or unstable NPU path silently replaces CPU. Mitigation:
  explicit profile; fallback to CPU on health failure.
- Driver/WSL gaps. Mitigation: treat undetected NPU as absent.

## Rollback

Disable the NPU profile; embedder, reranker, and ASR stay on CPU.

## Acceptance criteria

- Hardware profile can represent `npu: absent` or a detected device
  without breaking admission.
- CPU path unchanged when NPU is absent or the profile is off.
- Any on-by-default NPU placement has a local benchmark showing at
  least 20% improvement on the agreed metric, no quality regression,
  and no new critical reliability issue.
