# ADR-004: Resource Admission Control

- Status: Accepted
- Date: 2026-07-23

## Context

The GPU operates at ~98% VRAM with the default profile. Model switching
currently starts Compose profiles without checking whether weights, KV
cache, CUDA workspace, and runtime overhead fit available VRAM/RAM/storage
(audit risks R3, R4).

## Options considered

1. Status quo (implicit trust in profile sizing).
2. Static per-profile limits in Compose only.
3. Admission controller: budget model computed from
   `config/hardware-profile.json` + provider registry declarations
   (`minimum_vram`, context-derived KV budget, safety margin), evaluated
   before every provider start, with dry-run explanation.

## Evidence

- VRAM headroom measured at 507 MiB; a single context increase from 8K
  to 16K on the general model would exceed it.
- The audit found no OOM handling beyond container restart loops.

## Decision

Adopt option 3. Decisions: START, START_WITH_REDUCED_CONTEXT,
STOP_CONFLICTING_PROVIDER_AND_START, QUEUE, FALLBACK, REJECT.
Policy defaults for this workstation: at most one heavy GPU provider;
light services stay resident only while measured pressure permits;
stopping a production provider requires explicit policy opt-in; safety
margin defaults to 1 GiB VRAM and 4 GiB RAM.

`ai provider start <id> --dry-run` prints the decision, the budget
arithmetic, and the winning rule.

## Consequences

- KV-cache budgets become explicit per model/context; the 8K cap becomes
  a computed, documented value instead of folklore.

## Risks

- Budget model inaccuracies (CUDA workspace varies by engine). Mitigation:
  calibrate against measured `nvidia-smi` envelopes recorded by the
  benchmark harness; prefer conservative REJECT over optimistic START.

## Rollback

Config flag `admission.enforce=false` restores advisory-only mode
(log the decision, act as before).

## Acceptance criteria

- Unit tests cover all six decisions including insufficient-VRAM,
  insufficient-storage, and conflicting-provider cases.
- Dry-run output reviewed and documented in OPERATIONS.md.
