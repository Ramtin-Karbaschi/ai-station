# n8n on AI Station

n8n is an **optional** visual workflow client. It is not an inference
engine and not the operator console. Chat stays on Open WebUI
(`:3000`). Apps and agents stay on LiteLLM
(`http://127.0.0.1:4000/v1`). n8n is event-driven automation
(cron, webhook, HTTP) on `http://127.0.0.1:5678`.

ADR: [ADR-021](../adr/ADR-021-optional-n8n-automation-client.md)

## Start and stop

n8n is CPU-only and is not started by `ai start`. It can run next to
the active llama.cpp profile. A scheduled workflow can still consume
the GPU *through* LiteLLM when it calls a chat model.

~~~bash
ai n8n configure
ai provider start n8n --dry-run
ai n8n start
# browser: http://127.0.0.1:5678
ai n8n status
ai n8n stop
~~~

Windows Manager: **49** start, **50** stop, **51** open n8n.

First visit creates the n8n owner account on loopback. The station
does not store that password.

## LiteLLM / Instance AI

`ai n8n start` and `ai n8n configure` create (or reuse) the `n8n`
LiteLLM project key with `Qwen3.8-27B-UD-Q4_K_M`,
`Ornith-1.5-35B-Q4_K_M`, and `Qwen3-Embedding-8B-Q4_K_M`. The key is
written to `projects/n8n.env` (gitignored) and synced into `.env` as
`N8N_LLM_API_KEY`. LiteLLM virtual keys have **no TPM/RPM by default**
(ADR-029); `ai n8n configure` clears those caps on the n8n key. That is
not the 262144 context window. Compose maps the key into Instance AI:

- `N8N_INSTANCE_AI_MODEL=Qwen3.8-27B-UD-Q4_K_M` (bare name, not `openai/…`)
- `N8N_INSTANCE_AI_MODEL_URL=http://llm-gateway:4000/v1`
- `N8N_INSTANCE_AI_MODEL_API_KEY` from the virtual key
- SearXNG at `http://searxng:8080`
- Sandbox at `http://sandbox-api:8080` (n8n-sandbox; no host ports)

After start, `/assistant` should show Model, Code sandbox, and Web
search as **Found in server configuration**. Do not pick Anthropic,
OpenAI cloud, OpenRouter, or Daytona. If a Connect-a-model wizard
still opens, choose **Self-hosted or OpenAI-compatible endpoint**,
URL `http://llm-gateway:4000/v1`, model `Qwen3.8-27B-UD-Q4_K_M`,
and the Bearer token from `projects/n8n.env`.

Do not paste a sandbox API key into the UI. `ai n8n start` generates
`N8N_SANDBOX_SERVICE_API_KEY` in `.env` and injects
`N8N_SANDBOX_SERVICE_URL=http://sandbox-api:8080`. The Service
URL from n8n is on the Compose network, not
`http://sandbox.internal:3200` and not a host port.

The sandbox runner is privileged Docker-in-Docker and stays on the
internal Compose network. Daytona is not used. Browser Use is off.
Chat output is capped at 4096 tokens so a missing `max_tokens` cannot
run the GPU for tens of minutes. First Assistant turns still prefill a
large skill prompt; wait for the first tokens rather than sending
again.

HTTP Request nodes still need Header Auth (`N8N_BLOCK_ENV_ACCESS_IN_NODE`
stays true):

- Name: `Authorization`
- Value: `Bearer <LLM_API_KEY from projects/n8n.env>`

From n8n containers, POST to
`http://llm-gateway:4000/v1/chat/completions` with a canonical public
model name. From the host, use `http://127.0.0.1:4000/v1`. Never
`:8888` or a llama.cpp port.

## Station templates

Import JSON from `config/clients/n8n/workflows/` (also mounted
read-only at `/opt/ai-station-n8n-workflows` inside the container):

| File | What it does |
|---|---|
| `litellm-chat.json` | Manual trigger → LiteLLM chat |
| `tika-summarize.json` | Sample text → local Tika extract → LiteLLM summary |

IMAP/Gmail credentials stay in the n8n UI. Do not commit them.

## Data and uninstall

SQLite and the encryption key material live under
`/srv/ai-station/runtime/n8n`. `N8N_ENCRYPTION_KEY` is in `.env`.

~~~bash
ai n8n uninstall
ai n8n uninstall --purge --confirm
~~~

`--purge` deletes runtime workflow data only after `--confirm`. It
never deletes model bytes.

## Out of scope

Queue mode, extra Redis/Postgres, n8n Cloud templates, community
packages, and webhook exposure beyond loopback.
