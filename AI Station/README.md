# AI Station Windows Launchers

## Which file should I use?

| File | Role |
|---|---|
| **AI Station.cmd** | Quick start: start platform + open Open WebUI in your default browser. Platform stays running. |
| **AI Station Manager.cmd** | Full control panel: platform, models, API keys, LiteLLM UI login, logs, backup. |
| **AI Station Admin.cmd** | Compatibility alias → opens Manager. |

## Two different logins

| Product | URL | Purpose |
|---|---|---|
| Open WebUI | http://127.0.0.1:3000 | Human chat, document upload, RAG UI |
| LiteLLM Admin UI | http://127.0.0.1:4000/ui | Create/manage **application API keys** |

They are separate accounts.

### Open WebUI

Email on this workstation: `ramtin.karbaschi@gmail.com`
Reset from Manager option **26** if needed.

### LiteLLM Admin UI

1. Open Manager option **27. Show LiteLLM UI login**
2. Or open `\\wsl.localhost\Ubuntu\opt\ai-station\secrets\litellm_ui_credentials.txt`
3. Go to http://127.0.0.1:4000/ui
4. Username is `admin` (not your Gmail)

## What LiteLLM UI is for

Create separate Virtual Keys for different apps, for example:

- `docs-rag-api` → models `local-general`, `local-embedding`
- `email-agent-api` → model `local-general`

LiteLLM does **not** read your email or store your business documents by itself.
Your project code does retrieval / Gmail tools; LiteLLM authenticates and routes
model calls to the local llama.cpp runtime.

## Application endpoint

```text
http://127.0.0.1:4000/v1
```
