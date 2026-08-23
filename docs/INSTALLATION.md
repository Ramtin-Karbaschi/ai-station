# Installation Guide

AI Station installs the application into `/opt/ai-station` and stores models,
caches, and backups under `/srv/ai-station`. The remaining operator decision
is which local model fits the available GPU.

Supported hosts:

- Native Linux (Ubuntu-class + NVIDIA + Docker Engine)
- Windows 11 + WSL2 Ubuntu + Docker Desktop + NVIDIA Windows driver

Native Windows without WSL is not supported. macOS is out of scope until an
ADR and local CUDA-alternative benchmarks exist.

## Installation contract

This is a canonical-path install, not an arbitrary-path layout:

~~~text
/opt/ai-station     application, configuration, scripts
/srv/ai-station     models, caches, backups, runtime data
~~~

A clone may start in any temporary directory. The installer deploys into
those two roots, preserves `.env`, and keeps model bytes out of Git.

The station is **one Docker Compose project** named `ai-station`.
Operator entry is `ai start` (or `make start`). That starts the
application unit: Open WebUI, LiteLLM, PostgreSQL, Redis, Tika, SearXNG,
embeddings, and the reranker. Heavy llama.cpp profiles are the **same**
project with `--profile`. ComfyUI is the same project plus its overlay
file. Do not `docker run` these services ad hoc, and do not collapse
llama.cpp, LiteLLM, and Open WebUI into a single container.

Compose stays repository-relative. The canonical file chain is:

~~~text
COMPOSE_FILE=compose.yml:compose.models.yml:compose.hardening.yaml:compose.local-builds.yaml:compose.images.lock.yaml
~~~

References to `/opt/ai-station` are allowed only in files listed in
`config/release-path-allowlist.txt`.

Never commit `.env`, secrets, model binaries, databases, backups, caches,
or generated logs.

## Host prerequisites

The installer does **not** install NVIDIA drivers, WSL, or Docker.

### Linux

1. NVIDIA driver with `nvidia-smi` working.
2. Docker Engine and Compose v2.
3. NVIDIA Container Toolkit.
4. Git, Python 3, OpenSSL, curl, rsync, Bash.

~~~bash
nvidia-smi
docker version
docker compose version
~~~

### Windows 11 + WSL2

1. NVIDIA Windows driver.
2. WSL2 with an Ubuntu distribution.
3. Docker Desktop with WSL integration.
4. Confirm the GPU is visible **inside WSL**.

~~~bash
wsl.exe --status
docker version
docker compose version
nvidia-smi
~~~

Set `%UserProfile%\.wslconfig` so WSL does not idle-stop the stack:

~~~ini
[wsl2]
vmIdleTimeout=-1
~~~

`scripts/ai start` and `scripts/ensure-wsl-idle-timeout.sh` apply this
idempotently. After editing `.wslconfig`, run `wsl --shutdown` once from
PowerShell, then start AI Station again.

## Storage

Preflight requires at least 80 GiB free. The full model profile needs more
because the Hugging Face cache and the final GGUF may exist together.

Recommended baseline: ~24 GB VRAM, 64 GB RAM, NVMe storage. Smaller GPUs
can still run the station; choose a smaller GGUF in [MODELS.md](MODELS.md).

## Quick start

### Linux

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
~~~

Then choose models for this machine:

~~~bash
ai models catalog
make models-core
# or: ai models install <manifest-id>
~~~

### Windows 11

From PowerShell, after NVIDIA + WSL2 + Docker Desktop work:

~~~powershell
irm https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/windows/Install-AIStation.ps1 | iex
~~~

Day-to-day management: `Desktop\AI Station\AI Station Manager.cmd`.
Open WebUI: `http://127.0.0.1:3000`. Apps: `http://127.0.0.1:4000/v1`.

The Desktop `.cmd` files always run the panel in WSL
(`/opt/ai-station/AI Station/`). Do not keep a full copy of
`AI Station Manager.ps1` on the Desktop; it goes stale after upgrades.

Pack and bootstrap notes: [install/README.md](../install/README.md).

## Validate without modifying the system

~~~bash
./scripts/install.sh --validate-only
~~~

Do not continue until preflight reports:

~~~text
Errors:   0
Warnings: 0
INSTALLATION PREFLIGHT PASSED
~~~

## What the installer does

1. validates the host;
2. verifies container and Dockerfile locks;
3. creates application and data directories;
4. creates local configuration;
5. preserves an existing installation backup;
6. pulls immutable registry images;
7. builds repository-controlled images;
8. provisions the Core models;
9. verifies model checksums;
10. starts the stack;
11. waits for health checks.

Prepare without starting services:

~~~bash
sudo ./scripts/install.sh --prepare-only
~~~

Skip model checks only for infrastructure troubleshooting:

~~~bash
sudo ./scripts/install.sh --skip-model-check
~~~

## Verify after installation

~~~bash
cd /opt/ai-station
./scripts/verify.sh
~~~

## Upgrade

~~~bash
cd /opt/ai-station
git checkout development   # or stage / main, matching this machine
git pull --ff-only
sudo ./scripts/install.sh
~~~

When an existing application directory is replaced, the installer creates a
timestamped backup under `/srv/ai-station/backups`. The local `.env` file is
preserved.

## Clone this workstation onto another PC

1. Complete host prerequisites on the target.
2. Install with `install.sh` or the Windows bootstrap.
3. Optionally rsync `/srv/ai-station/models` to skip re-download; then
   `ai models verify <id>` or `./scripts/verify-models.sh --profile core`.
4. Generate fresh secrets on the new host unless you deliberately migrate
   them. Never copy a real `.env` into Git.

Acceptance on every new machine:

~~~text
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
./scripts/verify.sh
curl -fsS http://127.0.0.1:3000 >/dev/null
curl -fsS http://127.0.0.1:4000/health/liveliness >/dev/null
~~~

There is no supported single `.exe` that installs drivers, WSL, Docker, and
models. A future orchestrator can only check those prerequisites and then
run this installer.

## Clean-machine acceptance

1. Test installation on a disposable WSL distribution or Linux VM.
2. Verify host gateway services.
3. On Windows, confirm a full restart survives `wsl --shutdown`.
4. Test backup restoration.
5. Record the tested Git commit and model manifest checksums.
