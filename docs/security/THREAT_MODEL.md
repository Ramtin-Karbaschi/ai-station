# AI Station Threat Model

Date: 2026-07-23
Updated: 2026-07-24
Status: Phase 0 baseline plus Phase 1 mitigations (loopback bind, SSRF
guard). Review after any new public surface or engine adoption.

Scope: single-user local workstation (Windows 11 + WSL2), no intended
network exposure beyond the machine. Localhost binding is a mitigation,
not a security boundary: any process on the host, and the Windows side of
the WSL NAT, can reach loopback services.

## Trust zones

| Zone | Contents | Trust |
|---|---|---|
| Z1 Browser/UI | Open WebUI session | authenticated user |
| Z2 Containers | Compose services on `ai-station_default` / `ai-platform` | semi-trusted (pinned images, but upstream code) |
| Z3 Host services | gateway, UI gateway (systemd, run as root) | trusted code, elevated privilege |
| Z4 Data | `/srv/ai-station`, Docker volumes, secrets | protected |
| Z5 Internet | search upstreams, model/image registries | untrusted |

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
Controls: search result count capped at 3; RAG top-k 3; tools currently
disabled everywhere.
Gaps: when tool calling is enabled (Phase 1), injected content can invoke
tools. Actions: treat retrieved text as untrusted in system prompts;
require explicit user confirmation for state-changing tools; log tool-call
provenance.

### T3 Model supply-chain tampering

Path: poisoned GGUF/AWQ artifact or hijacked HF repo.
Controls: immutable HF revisions + SHA-256 in
`config/model-manifest.json`; verification script.
Gaps: 3 of 7 deployed model sets are outside the manifest and therefore
unverifiable (audit finding D2). Actions: Phase 1 manifest completion; new
engine artifacts (AWQ/GPTQ) must enter the same manifest discipline.

### T4 Poisoned container images

Controls: digest pinning for all registry images; local Tika build from a
digest-pinned base; GitHub Actions pinned to commit SHAs.
Gaps: digest refresh procedure trusts upstream tags at refresh time.
Actions: review upstream release notes at each `update-image-lock.sh` run;
keep the previous lock file in Git history for rollback.

### T5 SSRF through search and document tools

Path: the UI gateway fetches URLs found in chat payloads
(`fetch_url_bytes`) and SearXNG performs outbound queries. A crafted
message can point fetches at internal services (Postgres admin surfaces,
metadata endpoints, other loopback ports).
Controls: none specific today.
Actions (Phase 1): restrict UI-gateway fetches to the Open WebUI origin
and data URLs; deny non-HTTP schemes and RFC1918/loopback targets except
the explicit Open WebUI host; keep SearXNG outbound-only with its own
container network.

### T6 Exposed inference endpoints

Finding: gateway (8888) and UI gateway (8890) listen on `0.0.0.0`
(risk R1). Depending on WSL networking mode these are reachable from the
Windows host and possibly the LAN, unauthenticated.
Actions: bind to `127.0.0.1` (Phase 1); add a `verify.sh` assertion that
no AI Station listener is non-loopback; document that LiteLLM virtual keys
are the only authenticated API surface.

### T7 Arbitrary file access / path traversal

Path: model catalog and registry files drive `docker compose` invocations
from the gateway; filenames come from configuration, not user input.
Controls: models mounted read-only; catalog is root-owned.
Gaps: gateway runs as root and shells out to Compose; a compromised
catalog file becomes code execution. Actions: run gateway as a dedicated
user with Docker socket access consciously granted and documented; validate
catalog schema on load.

### T8 Command execution by agents

Not currently possible (no tools, no code interpreter). When enabled,
follow T2 actions plus an allowlisted tool registry; never expose shell
tools to models by default.

### T9 Secret leakage in logs

Controls: release audit greps for key patterns; secrets in files with
restrictive modes; LiteLLM salt/master keys via environment.
Gaps: gateway logs upstream error bodies (`response.text[:500]`) which may
echo request content; journald retains host-gateway logs indefinitely.
Actions: scrub Authorization headers in gateway logging; set journald
retention for the two units.

### T10 Unsafe model download paths

Controls: provisioning scripts write only under `/srv/ai-station/models`,
verify size + SHA-256, and use immutable revisions.
Gaps: interrupted-download and checksum-mismatch scenarios lack tests
(required by the testing plan, Phase 1).

## Non-goals

Multi-user isolation, internet-facing hardening, and DoS resistance are
out of scope for a single-operator workstation and are documented as such
in the README support matrix.
