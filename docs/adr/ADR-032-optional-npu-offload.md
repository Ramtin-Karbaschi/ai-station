# ADR-032: Optional NPU Offload for CPU-Class Workloads

- Status: Accepted
- Date: 2026-09-02
- Relates: [ADR-022](ADR-022-cpu-embedder-coexistence.md),
  [ADR-027](ADR-027-asr-primary-fallback.md)

## Context

CPU-class workloads may benefit from optional NPU offload, but the default
CPU path must remain available and stable.

## Options considered

1. Ignore NPU.
2. Move the heavy LLM onto NPU.
3. Detect NPU in the hardware profile. Keep GPU for heavy chat,
   vision, and ComfyUI. Allow an optional provider profile that
   places embed / rerank / ASR on NPU after a local apples-to-apples
   benchmark versus the current CPU path. If no NPU or the benchmark
   fails the 20% promotion rule, keep CPU.

## Evidence

Local capability checks and workload benchmarks are required before enabling
NPU offload. Record benchmark inputs, software prerequisites, and measured
results so the check can be repeated after runtime changes.

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
