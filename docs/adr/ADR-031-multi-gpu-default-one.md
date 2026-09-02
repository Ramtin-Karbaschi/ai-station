# ADR-031: Multi-GPU Capability With a One-GPU Default

- Status: Accepted
- Date: 2026-09-02
- Amends: [ADR-001](ADR-001-adaptive-inference-fabric.md),
  [ADR-004](ADR-004-resource-admission-control.md) (default unchanged
  on one-GPU hosts)

## Context

ADR-001 and ADR-004 assume one heavy GPU provider because this
workstation has one 24 GiB GPU at ~98% VRAM. The archived analysis
treated a second GPU as late failover hardware. The product must
**support several GPUs** while the **default remains one GPU**.

Operator choice for N>1 GPUs: concurrent heavy profiles (one per
GPU) as the default multi-GPU mode; tensor-parallel as explicit
configuration.

## Options considered

1. Keep one-GPU exclusivity forever; document a spare card as
   failover only.
2. Tensor-parallel as soon as a second GPU exists (one larger model).
3. Hardware profile lists GPUs. Default `max_heavy_providers = 1`.
   When GPU count is greater than one, admission may place one heavy
   profile per GPU (`gpu_index`). Tensor-parallel is a named profile
   or flag, off by default. ComfyUI still does not share a GPU with
   a llama.cpp heavy profile.

## Evidence

- Current `config/hardware-profile.json` has a single `gpu` object.
  Admission has no `gpu_index`.
- Concurrent engines on one 24 GiB card are still impossible; the
  one-GPU policy stays the default SKU.
- Tensor-parallel needs engine flags, matching quant, and a local
  benchmark before it can be a production default (provider
  benchmark policy).

## Decision

Adopt option 3.

## Consequences

- Wave 2 implements schema and admission changes.
- One-GPU hosts, including CI without extra cards, keep today's
  START / STOP_CONFLICTING / REJECT behavior.
- Dry-run must print which GPU would be used.

## Risks

- Incorrect placement oversubscribes one card. Mitigation: per-GPU
  VRAM budgets; prefer REJECT.
- Tensor-parallel on WSL2 is unverified. Mitigation: opt-in profile;
  promote only with `benchmarks/results/` evidence.

## Rollback

`max_heavy_providers = 1` and ignore extra GPUs. Same as today.

## Acceptance criteria

- Fixture-based tests cover one GPU and two GPUs without requiring
  a second physical card.
- Default install still starts a single heavy profile.
- Tensor-parallel is not selected unless the operator enables it.
- ComfyUI remains GPU-exclusive versus llama.cpp on the same index.
