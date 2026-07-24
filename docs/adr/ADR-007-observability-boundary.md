# ADR-007: Observability Boundary — Engine-Native Metrics, No External Telemetry

- Status: Accepted
- Date: 2026-07-23

## Context

An unused Prometheus scrape config exists (`infra/prometheus`) targeting a
service that no longer exists. Current visibility comes from healthchecks,
`verify.sh`, and `docker compose ps`.

## Options considered

1. No change.
2. Full stack (Prometheus + Grafana + exporters + tracing).
3. Minimal boundary: enable metrics endpoints the engines already ship
   (llama.cpp `--metrics`, LiteLLM, SGLang when trialed), one lightweight
   scraper with local retention, GPU/RAM sampling recorded by the
   benchmark harness, structured logs for admission decisions.

## Evidence

- Required signals (provider health, active model, VRAM/RAM, request
  counts/latency, TTFT, decode throughput, failures, restarts, admission
  decisions, model load time, disk pressure) are already exposed or
  derivable from the engines and Docker — no new instrumentation layer is
  needed to obtain them.
- A Grafana stack adds three containers and upgrade surface for a
  single-operator machine; benefit unproven.

## Decision

Adopt option 3. Explicit boundaries: no prompt or response content in
metrics or logs by default; no external telemetry of any kind; metrics
endpoints bind loopback/compose-network only. Prometheus itself is added
only if Phase 1-3 shows the file-based benchmark history is insufficient;
otherwise the dead config is removed.

## Consequences

- Observability lives in the same audit discipline: `verify.sh` asserts
  metric endpoints respond; benchmark history is the long-term store.

## Risks

- Under-observability during the SGLang trial. Mitigation: the trial's
  acceptance criteria include metric capture in the harness output.

## Rollback

Metrics flags are per-service command-line switches; removing them
restores current behavior.

## Acceptance criteria

- `verify.sh` covers metric endpoints of active providers.
- No collected metric contains prompt/response content (reviewed).
- Dead `infra/prometheus` config removed or activated — not left ambiguous.
