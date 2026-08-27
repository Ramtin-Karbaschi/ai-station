# Operations Guide

Run operational commands from:

~~~text
/opt/ai-station
~~~

## Platform CLI

The preferred control plane is the `ai` CLI:

~~~bash
ai status
ai start --profile general
ai restart
ai models use coder
ai models catalog
ai models add coder-ornith-1_5-35b
ai projects create my-app --models Qwen3.8-27B-UD-Q4_K_M,Qwen3-Embedding-8B-Q4_K_M
ai projects update opencode --models Ornith-1.5-35B-Q4_K_M,Qwen3.8-27B-UD-Q4_K_M,Qwen3.8-27B-Reasoning-UD-Q4_K_M
ai projects list
ai opencode configure
ai opencode test
ai graphify extract --code-only
ai graphify view
ai n8n start
ai output show
ai verify
ai verify --stability 45
~~~

Windows Desktop and Manager call this same `scripts/ai` entrypoint.
Application projects must call:

~~~text
http://127.0.0.1:4000/v1
~~~

or, from Docker Compose services attached to the external `ai-platform`
network:

~~~text
http://llm-gateway:4000/v1
~~~

Projects should request canonical public model names at that endpoint. Heavy
chat and vision names are accepted by LiteLLM, then routed through the host
gateway, which auto-switches the matching heavy runtime when needed.

See [PLATFORM.md](PLATFORM.md) for the multi-project control plane.
See [clients/OPENWEBUI.md](clients/OPENWEBUI.md) for Knowledge notebooks
versus `ai projects`.
See [SCRIPTS.md](SCRIPTS.md) for the canonical scripts map after cleanup.

## Command overview

~~~bash
make help
~~~

## Start

~~~bash
ai start
# or: ai start --profile general
~~~

`make start` and `./scripts/start.sh` are thin wrappers around the same CLI.

`ai start` brings up the single Compose project. Heavy GPU profiles
and ComfyUI are that same project, selected by profile or overlay,
not a second stack. n8n is the same project with Compose profile
`n8n` and is not started here.

The start flow restores the last heavy profile when `--profile` is omitted,
then waits for the main local endpoints before reporting readiness.

## Status

~~~bash
ai status
~~~

`make status` wraps the same command.

The status command displays:

- containers;
- endpoint probes (always-on and on-demand URLs, OK or DOWN);
- the service directory (addresses even when a tool is off);
- active heavy profile and free VRAM.

Disk and Docker usage are `ai disk`. systemd unit detail is `systemctl status
ai-station-gateway ai-station-ui-gateway`.

## Verification

~~~bash
make verify
~~~

The runtime is accepted only when all checks succeed.

## Logs

~~~bash
make logs
~~~

For a specific Compose service:

~~~bash
docker compose logs --tail=200 -f open-webui
docker compose logs --tail=200 -f llm-general
docker compose logs --tail=200 -f embedder
docker compose logs --tail=200 -f tika
~~~

Host gateway services:

~~~bash
journalctl -u ai-station-gateway -n 200 --no-pager
journalctl -u ai-station-ui-gateway -n 200 --no-pager
~~~

## Stop

~~~bash
ai stop
~~~

`make stop` / `./scripts/stop.sh` wrap the same command.

## Restart

~~~bash
ai restart
# preserves last heavy profile (or pass --profile ...)
~~~

`make restart` wraps the same command.

## Validate Compose

~~~bash
make config
~~~

## Build local images

~~~bash
make build
~~~

## Pull locked images

~~~bash
make pull
~~~

## Models

~~~bash
make models-core
make models-all
make models-verify
~~~

## Release audit

~~~bash
make audit
~~~

A valid release must finish with:

~~~text
Errors:   0
Warnings: 0
RELEASE AUDIT PASSED
~~~

## Backup policy

Backups must be written outside the repository under:

~~~text
/srv/ai-station/backups
~~~

A backup is not considered valid until:

1. all expected files exist;
2. checksums are generated;
3. the PostgreSQL dump can be listed or restored;
4. the Open WebUI data archive can be extracted;
5. a restore test is documented.

## Disk management

Inspect usage:

~~~bash
du -sh /srv/ai-station/models
du -sh /srv/ai-station/cache
docker system df
~~~

Do not run broad Docker cleanup commands without checking whether images or
volumes belong to AI Station.

## Safe update sequence

~~~bash
git status
git pull --ff-only
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
./scripts/verify.sh
./scripts/release-audit.sh
~~~

## Provider control plane

~~~bash
ai provider list
ai provider start llama-cpp-general --dry-run
ai provider doctor llama-cpp-coder
~~~

Host gateways bind to `127.0.0.1` via `scripts/install-systemd.sh`.
