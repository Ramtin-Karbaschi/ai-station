# Project State

Date: 2026-09-02
Status: Working pointer, not a runtime snapshot. Verified machine
state stays in
[ops/AI_STATION_CURRENT_STATE.md](ops/AI_STATION_CURRENT_STATE.md).

## Current goal

Turn AI Station into a sellable on-prem product using the sequence in
[ROADMAP.md](ROADMAP.md), under the constraints in
[PRODUCT.md](PRODUCT.md).

## Completed

- Wave D documents: PRODUCT, ROADMAP, DECISIONS, this file, ADR-030
  through ADR-034, disaster recovery and data-governance policies,
  digest of the external operational analysis under
  [research/AI_STATION_DEVELOPMENT_PLAN.md](research/AI_STATION_DEVELOPMENT_PLAN.md).

## In progress

- None.

## Next action

Start **Wave 0**: `ai restore --dry-run`, retention TTL, soft usage
alerts, lean health alerts. No new metrics containers.

## Blockers

- None for Wave D.
- Wave 2 multi-GPU CI must use fixtures; this host currently has one
  GPU in `config/hardware-profile.json`.
- Wave 2 NPU promotion is blocked on a local benchmark, not on docs.

## Verification

- Wave D: `./scripts/docs-audit.sh` on 2026-09-02 exited 0
  (`DOCUMENTATION AUDIT PASSED`; 27 required files; 3 mermaid
  diagrams).
- Later waves: focused tests first, then `make check`; runtime waves
  also need `ai verify`.

Do not mark a wave complete without command evidence in this file.
