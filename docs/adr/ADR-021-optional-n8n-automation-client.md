# ADR-021: n8n as an Optional Local Automation Client

- Status: Accepted
- Date: 2026-08-23

## Context

[PLATFORM.md](../PLATFORM.md) already describes automation agents
(email triage, tools, workflows) as LiteLLM clients that operators
build in their own Python/Node projects. That path stays valid. The
operator also wants a visual, event-driven workflow UI on the same
workstation so cron, webhooks, and HTTP steps can call the local
models without a second inference stack.

n8n is a fair-code workflow engine (Sustainable Use License) with an
official Docker image. It is not an inference engine. It is not an
operator console. Open WebUI remains interactive RAG/chat, OpenCode
remains the developer agent, and ComfyUI remains GPU media.

This workstation publishes services on loopback only. At most one
heavy GPU provider may run (ADR-004). n8n itself is CPU-only, but a
scheduled workflow can still consume the GPU *through* LiteLLM.

## Options considered

1. Do not add n8n; keep “build the agent in your own project” as the
   only automation path.
2. Start n8n with `ai start` (always-on). Cron and webhooks could
   GPU-swap llama.cpp with no operator at the keyboard.
3. Add Langflow, Flowise, or Dify as a second workflow UI.
4. Wrap n8n behind a new privileged web admin that can start GPU
   providers (rejected by ADR-016).
5. Add n8n as an isolated, off-by-default Compose profile: loopback
   `:5678`, digest-pinned registry image, SQLite under `/srv`,
   LiteLLM-only model calls, no tunnel or n8n Cloud templates.

## Evidence

- Official image `docker.n8n.io/n8nio/n8n`; documented current
  stable `2.35.6` (n8n Docker install docs, fetched 2026-08-23).
  License: Sustainable Use License (fair-code). Source:
  https://github.com/n8n-io/n8n
- n8n is CPU Node.js. It does not load GGUF weights. GPU use is
  only whatever LiteLLM routes when a workflow runs.
- OpenAI-compatible HTTP (`/v1/chat/completions`) is enough; n8n
  does not need `:8888` or llama.cpp ports.
- Community “n8n + local LLM” numbers are directional only. No
  apples-to-apples benchmark versus a custom Python agent is
  claimed. n8n is not promoted as a replacement for OpenCode or
  Open WebUI.

## Decision

Adopt option 5.

- Classification: **optional profile** (CPU workflow client).
- Compose: service `n8n` in `compose.yml` with `profiles: ["n8n"]`.
  `ai start` does not launch it. Image lock includes it via
  `--profile '*'`.
- Provider id `n8n`: `heavy: false`, `resource_group: cpu`. Do
  **not** set `compose_files` (that start path stops llama.cpp for
  ComfyUI). Starting n8n must not stop the active heavy profile.
- Bind `127.0.0.1:5678` only. No `--tunnel`, no LAN, no n8n Cloud
  template marketplace (`N8N_TEMPLATES_ENABLED=false`). Diagnostics
  and version notifications off.
- Persistence: SQLite + encryption key under
  `/srv/ai-station/runtime/n8n`. Do not share the Open WebUI /
  LiteLLM Postgres.
- Client contract: workflows call
  `http://llm-gateway:4000/v1` (Compose DNS) or
  `http://127.0.0.1:4000/v1` from the host. Canonical public model
  names only.
- Instance AI (n8n 2.35 `/assistant`) is pre-wired to LiteLLM:
  bare model `Qwen3.8-27B-UD-Q4_K_M`,
  `N8N_INSTANCE_AI_MODEL_URL=http://llm-gateway:4000/v1`,
  API key from the `n8n` LiteLLM project (`N8N_LLM_API_KEY`).
  Sandbox is the official n8n-sandbox stack on the Compose network
  (`http://sandbox-api:8080`, no host ports, no Daytona). The runner
  is privileged Docker-in-Docker. `ai n8n start` generates
  `N8N_SANDBOX_SERVICE_API_KEY` and recreates n8n so env applies.
  SearXNG uses Compose DNS `http://searxng:8080`. `ai n8n start`
  also creates the LiteLLM project key.
- Station templates: importable JSON under
  `config/clients/n8n/workflows/` (LiteLLM chat; Tika then
  summarize). Operator adds IMAP/Gmail credentials in the n8n UI.
- CLI: `ai n8n start|stop|status|configure|uninstall`. Windows
  Manager calls the same CLI. First-run owner account is created
  in the browser on loopback; the station does not auto-provision
  that password.
- Admission: skip VRAM checks for non-heavy providers. RAM and
  storage checks remain.
- Uninstall: stop/remove the container. `--purge --confirm`
  deletes runtime data. Never delete model bytes.

## Consequences

Operators get a visual automation client next to LiteLLM without a
fourth core layer. Scheduled n8n jobs can still swap the heavy GPU
via LiteLLM auto-switch; that is documented, not a start-time
stop of llama.cpp. OpenCode, Open WebUI, and ComfyUI stay in their
workload classes.

## Risks

- Workflow HTTP nodes can SSRF loopback services (Postgres,
  LiteLLM master key surfaces). Mitigation: loopback bind,
  `N8N_BLOCK_ENV_ACCESS_IN_NODE=true`, community packages off,
  operator-owned credentials, LiteLLM virtual key with an
  allowlist.
- Encryption-key loss decrypts no credentials. Mitigation: key in
  `.env` (`N8N_ENCRYPTION_KEY`), data dir under `/srv`.
- n8n Cloud / telemetry. Mitigation: templates, diagnostics,
  version notifications, and personalization off; no tunnel.
- Instance AI sandbox runner is privileged Docker-in-Docker.
  Mitigation: Compose profile `n8n` only, no published sandbox
  ports, generated API keys in `.env`, no Daytona.
- License is not MIT. Mitigation: record Sustainable Use License
  in `THIRD_PARTY_NOTICES.md`; workstation-internal use only.

## Rollback

~~~bash
ai n8n uninstall --purge --confirm
~~~

Leave `compose.yml` service unused (`profiles: ["n8n"]`). Image
lock pin can stay until the next lock refresh.

## Acceptance criteria

1. `ai start` does not start n8n.
2. `ai provider start n8n --dry-run` returns `START` while a
   llama.cpp heavy profile is active and free VRAM is below the
   GPU safety margin.
3. `ai n8n start` publishes only `127.0.0.1:5678` and
   `GET /healthz` succeeds.
4. Pinned workflows name `http://llm-gateway:4000/v1` and a
   canonical public model id; they never name `:8888`.
5. `ai n8n uninstall` stops the container; `--purge --confirm`
   removes `/srv/ai-station/runtime/n8n`.
6. Digest pin for `n8n` exists in `compose.images.lock.yaml`.
