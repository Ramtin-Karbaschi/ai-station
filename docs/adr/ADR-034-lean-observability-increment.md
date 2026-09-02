# ADR-034: Lean Observability Increment

- Status: Accepted
- Date: 2026-09-02
- Amends: [ADR-007](ADR-007-observability-boundary.md) (next
  increment only; no SaaS telemetry still holds)

## Context

ADR-007 chose engine-native metrics, no external telemetry, and
deferred Prometheus unless file-based history was insufficient. An
unused Prometheus config was removed rather than activated. The
archived analysis proposed Prometheus + Grafana + Loki as the first
fix. That stack adds containers, image upgrades, and log/index disk.
The operator asked for a small next step.

Required first signals: CUDA OOM, always-on container down, disk
above 85%, plus the usage alerts in ADR-033. Those are already
derivable from Docker, healthchecks, `ai status` / `ai disk`, and
LiteLLM spend.

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

Adopt option 3.

## Consequences

- Wave 0 owns the alerter. Retention and max bytes must be in the
  implementation doc and a test.
- No prompt or response content in alerts (ADR-007 boundary).
- OpenTelemetry exporters, Loki, and Grafana dashboards are not
  Wave 0-2 work.

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
