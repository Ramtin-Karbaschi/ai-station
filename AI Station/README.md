# AI Station Windows Launchers

These files live in the repository. Desktop shortcuts must call the copies
under `\\wsl.localhost\Ubuntu\opt\ai-station\AI Station\` so they cannot go
stale after an upgrade.

## Which file should I use?

| File | Role |
|---|---|
| **AI Station.cmd** | Quick start: start platform + open Open WebUI |
| **AI Station Manager.cmd** | Control panel: lifecycle, models, API keys, logs, backup |

The `.cmd` files pass typed arguments into WSL. They do not keep a second
copy of the PowerShell panel on the Desktop.

In addition to lifecycle operations, the panel provides catalog / install /
add / quarantine / restore, offline tests, Graphify, and the non-root WSL
OpenCode developer client. Clients option 28 runs the verified developer
client; option 32 repairs its pinned runtime and config.

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
