# ADR-031: Multi-GPU Capability With a One-GPU Default

- Status: Accepted
- Date: 2026-09-02
- Amends: [ADR-001](ADR-001-adaptive-inference-fabric.md),
  [ADR-004](ADR-004-resource-admission-control.md) (default unchanged
  on one-GPU hosts)

## Context

The default single-GPU configuration must remain predictable while
multi-GPU hosts need explicit placement behavior.

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

- The workstation exposes one NVIDIA GPU to WSL. A disposable Docker Compose
  container confirmed that reservation of GPU `0` exposes that device.
- Two-GPU fixtures confirmed that different placements preserve the active
  provider, the new Compose process receives the admitted device index, and
  malformed or all-device reservations prevent concurrent startup. Physical
  GPU `1` is required to validate a second runtime on this workstation.
- Concurrent engines on one 24 GiB card are still impossible; the
  one-GPU policy stays the default SKU.
- Tensor-parallel needs engine flags, matching quant, and a local
  benchmark before it can be a production default (provider
  benchmark policy).

## Decision

Adopt option 3.

## Consequences

- The Gateway uses a per-device free-VRAM probe and passes the selected
  `gpu_index` to Docker for each managed launch. Before allowing concurrent
  heavy workloads it checks the Docker reservation of providers that would
  keep running. Legacy all-device containers require a controlled restart
  onto an explicit device before they can coexist with another provider.
- One-GPU hosts, including CI without extra cards, keep today's
  START / STOP_CONFLICTING / REJECT behavior.
- CLI model switching remains serialized. Dry-run prints the assigned index.
- The managed launch refuses explicit tensor-parallel requests until a backend
  has a tested multi-device launch contract.

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
