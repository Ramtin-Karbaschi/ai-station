# ADR-034: Lean Observability Increment

- Status: Accepted
- Date: 2026-09-02
- Amends: [ADR-007](ADR-007-observability-boundary.md) (next
  increment only; no SaaS telemetry still holds)

## Context

Existing health probes and status output provide the foundation for
operational visibility. Additional signals must remain bounded and use
short-lived retention.

## Options considered

1. Install Prometheus, Grafana, and Loki now.
2. Enable every engine `/metrics` plus a long-retention scraper.
3. Wave 0: evaluate existing probes on a schedule; write short-lived
   local alert state (hours to a few days, size-capped); no new
   Compose service. Prometheus/Grafana/Loki stay out of scope until
   this layer is shown insufficient in an ADR with disk measurements.

## Evidence

- ADR-007: a Grafana stack is three containers whose benefit on a
  single-operator machine was unproven.
- Healthchecks and `verify.sh` already exist; they do not page the
  operator today.

## Decision

Reuse existing probes, evaluate them on a schedule, and report actionable
failures through the station's current operator surfaces. Keep telemetry
bounded, retain it briefly, and do not add an always-on service for this
function.

## Consequences

- Existing probes remain the source of health information.
- Retention limits and maximum storage size are explicit configuration.
- Operators can inspect alerts through current station surfaces.

## Risks

- Under-observability for latency SLOs. Mitigation: revisit only
  with a measured gap; llama.cpp `/metrics` may be enabled later
  without Grafana.
- Alert state filling the data root. Mitigation: size cap and
  rotate; refuse to log request bodies.

## Rollback

Stop the alerter loop. Healthchecks and `ai verify` remain.

## Acceptance criteria

- No new always-on container in Wave 0.
- Alerts for disk 85%, CUDA OOM (from logs or nvidia-smi), and
  always-on container exit.
- Retention cap documented and enforced.
- `verify.sh` still passes with the alerter on or off.
