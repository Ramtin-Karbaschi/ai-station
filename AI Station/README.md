# AI Station Windows Launchers

## Which file should I use?

| File | Role |
|---|---|
| **AI Station.cmd** | Quick start: start platform + open Open WebUI in your default browser |
| **AI Station Manager.cmd** | Control panel: platform, models, API keys, logs, backup |
| **AI Station Admin.cmd** | Compatibility alias → opens Manager |

The Manager `.cmd` is a stable launcher for a typed PowerShell control panel.
It passes command arguments directly through WSL without constructing
`bash -lc` strings. In addition to normal lifecycle operations, the panel
provides catalog/install/add/quarantine/restore, offline tests, Graphify, and
the non-root WSL OpenCode developer client. Clients option 28 runs the
verified developer client; option 32 repairs its pinned runtime/config.

## Two different logins

| Product | URL | Purpose |
|---|---|---|
| Open WebUI | http://127.0.0.1:3000 | Human chat, documents, RAG |
| LiteLLM Admin UI | http://127.0.0.1:4000/ui | Application API keys |

They are separate accounts. Create the first Open WebUI user on first visit.
LiteLLM admin credentials are generated at install time under:

~~~text
\\wsl.localhost\Ubuntu\opt\ai-station\secrets\litellm_ui_credentials.txt
~~~

(Manager menu can also show them.)

## Application endpoint

~~~text
http://127.0.0.1:4000/v1
~~~
