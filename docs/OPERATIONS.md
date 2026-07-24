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
ai models use coder
ai models active
ai projects create my-app --models local-general,local-embedding
ai projects list
ai verify
~~~

Application projects must call:

~~~text
http://127.0.0.1:4000/v1
~~~

or, from Docker Compose services attached to the external `ai-platform`
network:

~~~text
http://llm-gateway:4000/v1
~~~

See [PLATFORM.md](PLATFORM.md) for the multi-project control plane.
See [SCRIPTS.md](SCRIPTS.md) for the canonical scripts map after cleanup.

## Command overview

~~~bash
make help
~~~

## Start

~~~bash
make start
~~~

or:

~~~bash
./scripts/start.sh
~~~

The start flow waits for the main local endpoints before reporting readiness.

## Status

~~~bash
make status
~~~

or:

~~~bash
./scripts/status.sh
~~~

The status command displays:

- containers;
- systemd services;
- endpoint checks;
- disk usage;
- Docker disk usage.

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
make stop
~~~

or:

~~~bash
./scripts/stop.sh
~~~

## Restart

~~~bash
make restart
~~~

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
