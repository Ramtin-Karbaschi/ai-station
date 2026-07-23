# ADR-001: Adopt a Reduced Adaptive Inference Fabric

- Status: Proposed
- Date: 2026-07-23

## Context

AI Station runs one inference engine (llama.cpp) with model switching,
lifecycle, and exclusivity logic embedded in the host gateway. A candidate
"Adaptive Inference Fabric" with six planes (experience, control,
inference, retrieval, document intelligence, observability) was evaluated
against the Phase 0 audit ([AI_STATION_ARCHITECTURE_AUDIT.md](../research/AI_STATION_ARCHITECTURE_AUDIT.md)).

## Options considered

1. Keep the current implicit architecture unchanged.
2. Full fabric: registry, scheduler, router, policy engine, health
   manager, multiple concurrent engines.
3. Reduced fabric: declarative provider registry, admission controller
   with dry-run, lifecycle CLI, benchmark registry; single active heavy
   engine preserved; other planes retained as-is.

## Evidence

- The gateway already performs scheduling (stop-others/start/poll) —
  the control plane exists but is unmaintainable as embedded constants.
- The GPU runs at 98% VRAM with one heavy model; concurrent heavy engines
  are physically impossible on this hardware, so a full scheduler/router
  has no workload to schedule.
- Reproducibility and audit tooling are strong and must not be disrupted.

## Decision

Adopt option 3. Extract what exists into declarative form; add only
admission control and benchmarking as genuinely new capabilities. Defer
routers, policy engines, and multi-engine concurrency until a second
production engine exists and evidence demands them.

## Consequences

- Phase 1 is mostly refactoring plus hygiene; runtime behavior preserved.
- Any future engine (SGLang, TensorRT-LLM) plugs into the registry rather
  than the gateway source.

## Risks

- Over-abstraction if the registry grows speculative fields. Mitigation:
  schema v1 contains only fields consumed by working code.

## Rollback

The registry-driven gateway ships alongside the constant-driven code path
behind a config flag until Phase 1 acceptance; reverting is a one-line
config change and a service restart.

## Acceptance criteria

- Identical observable behavior before/after extraction (contract tests).
- Admission dry-run explains decisions for all six decision types.
- Release audit: Errors 0, Warnings 0.
