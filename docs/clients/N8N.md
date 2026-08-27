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

## LiteLLM credential

`ai n8n configure` creates (or reuses) the `n8n` LiteLLM project key
with `Qwen3.8-27B-UD-Q4_K_M`, `Ornith-1.5-35B-Q4_K_M`,
and `Qwen3-Embedding-8B-Q4_K_M`. Credentials live in
`projects/n8n.env` (gitignored).

In n8n, add HTTP Header Auth:

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
