# ADR-029: No Default LiteLLM TPM/RPM on Operator-Owned Keys

- Status: Accepted
- Date: 2026-08-29

## Context

This station is a single-operator loopback workstation. Every LiteLLM
virtual key is created by the operator for a local client (n8n,
OpenCode, content studio, and other `projects/*.env` apps). LiteLLM
still applied SaaS-style defaults on `/key/generate`: **100000 tokens
per minute** and **60 requests per minute**.

n8n Instance AI prefills tens of thousands of tokens per turn. A few
retries exhausted the 100000 TPM budget even though Qwen3.8 general
advertises a **262144** context window. Raising only the n8n key to
256000 left every other project on the old cap.

## Options considered

1. Keep 100000 TPM / 60 RPM as a safety default; raise individual keys.
2. Raise the default to a large number (for example 256000 or
   2_000_000_000) so limits remain but rarely trip.
3. Omit TPM/RPM on generate (`null` in LiteLLM) so virtual keys are
   unlimited unless the operator passes `--tpm`/`--rpm`. Clear existing
   keys with `ai projects unlimit`.

## Evidence

- LiteLLM `/key/list?return_full_object=true` on 2026-08-29 showed
  mixed caps: n8n 256000/60, content-studio and opencode 100000/60,
  company-os 50000/10, cursor 200000/30, demo-app 100000/120. Some
  manually created keys already had `tpm_limit: null`.
- Official LiteLLM `/key/update` accepts `"tpm_limit": null,
  "rpm_limit": null` and returns those fields as `null`, which
  disables the limiter. The hashed `token` from `/key/list` is a valid
  `key` argument for that update.
- The GPU, not LiteLLM TPM, is the real throughput limit on this host
  (ADR-004). A proxy token bucket does not protect VRAM.

## Decision

Adopt option 3. Isolation stays on **model allowlists**, loopback
binds, and per-project revocation. Rate limits are an explicit opt-in.

## Consequences

- `ai projects create` does not send `tpm_limit` or `rpm_limit`.
- `ai projects unlimit` clears TPM/RPM on every virtual key (or
  `--alias <id>`).
- n8n configure clears the n8n key; it does not re-apply a TPM cap.
- Open WebUI already uses the master key, which had no TPM/RPM.

## Risks

- A buggy client can send unbounded request volume through `:4000`.
  Mitigation: loopback only; one heavy GPU; operator can still pass
  `--tpm`/`--rpm` on a specific key.
- Cached LiteLLM key objects could keep an old cap until update.
  Mitigation: `unlimit` writes `null` on the live `/key/update` path.

## Rollback

Create or update a key with explicit caps:

~~~bash
ai projects create <id> --models <names> --tpm 100000 --rpm 60
~~~

Existing keys cannot restore a previous number automatically; set
`--tpm`/`--rpm` again via LiteLLM `/key/update` if a cap is required.

## Acceptance criteria

- Default generate payload omits `tpm_limit` and `rpm_limit`.
- `ai projects unlimit` reports `tpm=none rpm=none` for listed keys.
- Contract tests cover the unlimited default and the n8n unlimit path.
