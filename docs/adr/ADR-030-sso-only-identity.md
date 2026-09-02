# ADR-030: SSO-Only Identity for Human Users

- Status: Accepted
- Date: 2026-09-02

## Context

Open WebUI today uses local username/password (`WEBUI_AUTH: "True"`).
Application projects use LiteLLM virtual keys. The archived product
analysis asked for RBAC plus LDAP or OIDC. The operator approved
**SSO only**. Shared local end-user accounts are not acceptable for a
sold product. LDAP is rejected.

## Options considered

1. Keep local passwords and optional shared accounts.
2. LDAP / Active Directory bind for Open WebUI groups.
3. OIDC SSO as the only supported human identity path; map IdP groups
   to Admin / Member / Viewer; keep one local break-glass operator
   for bootstrap and recovery; leave LiteLLM project keys as machine
   credentials.

## Evidence

- Open WebUI already supports OIDC; LDAP would be a second identity
  plane for one problem.
- LiteLLM keys isolate applications (ADR-029, PLATFORM.md). They are
  not people. Mixing them with human SSO would blur revocation.
- Loopback-only binds remain; SSO talks to a customer IdP the operator
  configures. The station does not become a public IdP.

## Decision

Adopt option 3. LDAP is out of scope. Customer end users sign in
through OIDC. Role comes from group claims, not a station-local user
directory. The break-glass operator account is for install and DR,
not for daily use.

## Consequences

- Wave 1 in [ROADMAP.md](../ROADMAP.md) implements this ADR.
- Docs and compose must not advertise LDAP.
- Project keys at `:4000/v1` stay as they are.

## Risks

- A broken IdP locks out end users. Mitigation: break-glass operator,
  documented in [ops/DISASTER_RECOVERY.md](../ops/DISASTER_RECOVERY.md).
- Mis-mapped groups grant Admin. Mitigation: default to Viewer;
  explicit group allowlists.

## Rollback

Disable OIDC env on Open WebUI, restore local auth for the operator,
and recycle the container. Existing LiteLLM keys are unchanged.

## Acceptance criteria

- A user completes login against a configured OIDC issuer.
- Unmapped users do not receive Admin.
- LDAP modules, images, and docs are absent from the supported path.
- Prompt and response content are not written to the login log.
