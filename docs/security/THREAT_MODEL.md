# AI Station Threat Model

Date: 2026-07-23
Updated: 2026-08-22, 2026-08-23
Status: implemented controls plus residual risks. Review after any new public
surface, runtime engine, model capability, or agent tool adoption.

Scope: single-user local workstation (Windows 11 + WSL2). Project-managed
services remain loopback-only.
Localhost binding is a mitigation, not a security boundary: any process on the
host, and the Windows side of the WSL NAT, can reach loopback services.

## Trust zones

| Zone | Contents | Trust |
|---|---|---|
| Z1 Browser/UI | Open WebUI session | authenticated user |
| Z2 Containers | Compose services on `ai-station_default` / `ai-platform` | semi-trusted (pinned images, but upstream code) |
| Z3 Host services | gateway, UI gateway (systemd, run as root) | trusted code, elevated privilege |
| Z4 Data | `/srv/ai-station`, Docker volumes, secrets | protected |
| Z5 Internet | search upstreams and model/image registries | untrusted/external |

## Threats, current controls, gaps

### T1 Malicious uploaded documents

Path: upload -> Tika/Tesseract (JVM parses attacker-controlled bytes) ->
chunks -> LLM context.
Controls: Tika runs in a container with a 3 GiB JVM cap and
`ExitOnOutOfMemoryError`; file size/count limits in Open WebUI.
Gaps: Tika container capabilities not minimized; no timeout budget per
document in the UI gateway path (600 s is generous); parser CVEs arrive
through the pinned image only when the lock is refreshed.
Actions: add no-new-privileges and capability drop to the Tika service;
tighten UI-gateway extraction timeout; include Tika in lock-refresh cadence.

### T2 Prompt injection through retrieved content

Path: web search results (SearXNG) or RAG chunks carry instructions that
steer the model, potentially triggering tool calls once tools are enabled.
Controls: search result count capped at 3; RAG injects at most 3 chunks
after rerank from a 20-candidate pool; application API keys
have explicit model allowlists. OpenCode agent tools run in the user's project
context, not inside the inference service.
Gaps: agentic coder/general/Ornith models can act on injected instructions when
the client grants tools. Actions: treat retrieved text as untrusted in prompts;
require explicit user confirmation for state-changing tools; log tool-call
provenance.

### T3 Model supply-chain tampering

Path: poisoned GGUF/AWQ artifact or hijacked HF repo.
Controls: immutable HF revisions + SHA-256 in
`config/model-manifest.json`; verification script.
Current state: all catalogued model artifacts use immutable revisions and
SHA-256 metadata. New engine artifacts (AWQ/GPTQ/GGUF) must enter the same
manifest discipline before promotion.

### T4 Poisoned container images

Controls: digest pinning for all registry images; local Tika build from a
digest-pinned base; quality gates stay local (`make check`).
Gaps: digest refresh procedure trusts upstream tags at refresh time.
Actions: review upstream release notes at each `update-image-lock.sh` run;
keep the previous lock file in Git history for rollback.

### T5 SSRF through search and document tools

Path: the UI gateway fetches URLs found in chat payloads
(`fetch_url_bytes`) and SearXNG performs outbound queries. A crafted
message can point fetches at internal services (Postgres admin surfaces,
metadata endpoints, other loopback ports).
Controls: UI-gateway fetches are restricted to the explicit Open WebUI origin;
non-HTTP schemes and arbitrary RFC1918/loopback targets are denied. SearXNG is
kept behind the local container/loopback boundary.
Residual risk: an allowed upstream may redirect or return hostile content;
retain bounded timeouts and treat fetched bytes as untrusted.

### T6 Exposed inference endpoints

Current state: application listeners bind to `127.0.0.1`. The host gateway has
one deliberate TCP mirror on the exact private `docker0` address so containers
can reach the loopback application; wildcard and LAN binds fail verification.
LiteLLM virtual keys on `:4000` are the authenticated application surface;
`:8888` remains an internal routing endpoint and must never be configured as a
client API. Virtual keys do not carry TPM/RPM unless the operator sets them
(ADR-029); loopback binding is the volume control.

### T7 Arbitrary file access / path traversal

Path: model catalog and registry files drive `docker compose` invocations
from the gateway; filenames come from configuration, not user input.
Controls: models mounted read-only; catalog is root-owned.
Gaps: gateway runs as root and shells out to Compose; a compromised
catalog file becomes code execution. Actions: run gateway as a dedicated
user with Docker socket access consciously granted and documented; validate
catalog schema on load.

### T8 Command execution by agents

OpenCode can execute developer tools under the user's authority. The inference
runtime itself receives tool schemas but has no direct shell privilege.
Controls belong at the client/agent boundary: project-scoped working directory,
review of destructive operations, minimal connector permissions, and no secret
material in prompts. Never expose an unaudited shell tool through the shared
LiteLLM application API by default.

### T9 Secret leakage in logs

Controls: release audit greps for key patterns; secrets in files with
restrictive modes; LiteLLM salt/master keys via environment. Gateway contract
telemetry records endpoint shape, counts, status, latency-relevant state, and a
normalized error category, never message bodies or raw upstream errors.
Residual risk: journald retains host-gateway logs according to host policy.
Actions: keep Authorization headers and prompt bodies out of telemetry; set a
bounded journald retention policy if this workstation becomes multi-user.

### T10 Unsafe model download paths

Controls: provisioning scripts write only under `/srv/ai-station/models`,
verify size + SHA-256, and use immutable revisions.
Gaps: interrupted-download and checksum-mismatch scenarios lack tests
(required by the testing plan, Phase 1).

### T11 Loopback Graphify map

`ai graphify view` serves static HTML from the Graphify output directory on
`127.0.0.1:4174`. It does not start GPU providers or expose secrets.
Controls: loopback bind, directory limited to the generated graph folder,
`--stop` tears the listener down. Residual risk: any local process can
read `graph.json` (already on disk). Do not bind `:4174` on `0.0.0.0`.

### T12 n8n workflow SSRF and credential store

n8n on `127.0.0.1:5678` can issue HTTP from the Compose network
(LiteLLM, Tika, Postgres, Redis). Workflows are operator-authored.
Controls: loopback publish; `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`;
community packages and Cloud templates off; no tunnel; LiteLLM virtual
key with a model allowlist; SQLite under `/srv/ai-station/runtime/n8n`.
Gaps: a local process can open `:5678` after the owner account exists;
webhook paths remain loopback-only by policy. Do not bind `:5678` on
`0.0.0.0` and do not enable n8n `--tunnel`.

## Non-goals

Multi-user isolation, general-purpose internet-facing hosting, and strong DoS
resistance are out of scope.
