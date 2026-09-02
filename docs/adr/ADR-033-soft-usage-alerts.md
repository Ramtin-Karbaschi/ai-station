# ADR-033: Soft Usage Alerts Without Default Rate Caps

- Status: Accepted
- Date: 2026-09-02
- Does not amend: [ADR-029](ADR-029-no-default-litellm-tpm-rpm.md)
  (unlimited virtual keys remain the default)

## Context

ADR-029 removed default LiteLLM TPM/RPM because the GPU, not a proxy
token bucket, is the real limiter, and n8n-scale prompts exhausted
100000 TPM. The archived analysis asked for a substitute so leaked
keys and retry loops are visible. The operator forbids reducing
throughput. Alerts and monitoring are allowed.

## Options considered

1. Restore default TPM/RPM.
2. Leave unlimited keys with no signal.
3. Keep unlimited keys. Alert when a key's tokens or requests in a
   window exceed about 3x its recent daily mean (operator-tunable).
   Never reject or delay a request because of this signal.

## Evidence

- ADR-029: LiteLLM `/key/update` with null TPM/RPM disables the
  limiter; GPU admission is the capacity control.
- LiteLLM already stores spend / usage for virtual keys. That table
  is enough for a threshold without a new telemetry pipeline.

## Decision

Adopt option 3. Wave 0 implements the alert. ADR-029 stays accepted.

## Consequences

- `ai projects create` still omits `tpm_limit` / `rpm_limit`.
- Operators may still pass `--tpm` / `--rpm` for a specific key.
- Alert delivery in Wave 0 is local (log, `ai` status, or operator
  notification already used by the station). No SaaS webhook
  requirement.

## Risks

- A new key has no mean; 3x is undefined. Mitigation: warm-up
  window; alert on a large absolute floor until a mean exists.
- Alert fatigue. Mitigation: one firing per key per window.

## Rollback

Disable the alerter. Keys remain unlimited. No limiter to re-enable.

## Acceptance criteria

- Contract tests show a request succeeds when the alert would fire.
- Default generate payload still omits TPM/RPM.
- Documented dry-run or test can show an alert without sending
  prompt text.
