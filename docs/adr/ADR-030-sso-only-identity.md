# ADR-030: SSO-Only Identity for Human Users

- Status: Accepted
- Date: 2026-09-02

## Context

Human users need a consistent sign-in path for the station control plane.
Local identities and directory protocols add account lifecycle and recovery
work. The service API has a separate project-key boundary.

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
- On 2026-11-22 a disposable Open WebUI instance completed signed OIDC
  login with Dex in an isolated network namespace. An unmapped group was
  refused. Changing the allowed and administrator groups mapped the same
  synthetic identity to Open WebUI `user` and then `admin`. After Dex stopped, the
  local break-glass operator could still sign in as Admin. Customer issuer
  configuration and customer-group acceptance require a separate drill.

## Decision

Adopt option 3. LDAP is out of scope. Customer end users sign in
through OIDC. Role comes from group claims, not a station-local user
directory. The break-glass operator account is for install and DR,
not for daily use.

## Consequences

- Authorization roles come from trusted OIDC group claims.
- Production issuer and group mappings require operator validation before use.
- The setup command requires an active local password Admin and pre-created
  Open WebUI groups for all three Station roles. OAuth group creation and
  account merging by email stay disabled.
- Open WebUI maps Admin to `admin`, while Member and Viewer map to `user`;
  their separate group memberships support group-specific permissions.
- LiteLLM virtual keys remain separate from human sign-in.

## Risks

- A broken IdP locks out end users. Mitigation: break-glass operator,
  documented in [ops/DISASTER_RECOVERY.md](../ops/DISASTER_RECOVERY.md).
- Mis-mapped groups can grant Admin. Open WebUI uses explicit allowlists for
  sign-in and elevation. Member and Viewer share Open WebUI's `user` role.
  Keep `OAUTH_MERGE_ACCOUNTS_BY_EMAIL` off so an IdP user cannot inherit
  the break-glass admin. Create the local
  operator before enabling OAuth signup (Open WebUI promotes the
  first user to admin). `ai sso configure` refuses when `auth` is
  empty or postgres is unreachable.

## Rollback

Disable OIDC env on Open WebUI, restore local auth for the operator,
and recycle the container. Existing LiteLLM keys are unchanged.

## Acceptance criteria

- A user completes login against a configured OIDC issuer.
- Missing and unmapped role claims are denied, including during first-user
  bootstrap.
- Successful login audit records omit tokens, prompts, and chat content.
- LDAP modules, images, and docs are absent from the supported path.
- Prompt and response content are not written to the login log.
