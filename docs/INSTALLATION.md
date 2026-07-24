# Installation Guide

This guide describes the supported AI Station installation flow.

See also [Multi-machine deployment](MULTI_MACHINE_DEPLOYMENT.md) for cloning
this workstation onto another PC, and what a future Windows `.exe` bootstrap
can (and cannot) automate.

## Supported installation layout

~~~text
/opt/ai-station
/srv/ai-station
~~~

The repository may initially be cloned elsewhere. The installer deploys the
application into `/opt/ai-station` and stores models, caches and backups under
`/srv/ai-station`.

## Before installation

The installer does not install or configure the Windows NVIDIA driver,
WSL2 or Docker Desktop.

Complete these host-level prerequisites first:

1. Install or enable WSL2.
2. Install an Ubuntu-based WSL distribution.
3. Install Docker Desktop or Docker Engine.
4. Enable Docker integration for the WSL distribution.
5. Install a compatible Windows NVIDIA driver.
6. Confirm the GPU is visible inside WSL.

Verify:

~~~bash
wsl.exe --status
docker version
docker compose version
nvidia-smi
~~~

## Required tools

The installation expects:

- Bash;
- Git;
- Docker;
- Docker Compose v2;
- Python 3;
- OpenSSL;
- curl;
- rsync;
- `nvidia-smi`.

Missing basic Ubuntu packages may be installed automatically by the installer.

## Storage requirements

The configured preflight requires at least 80 GiB of free storage.

The full model profile requires substantially more space than the Core profile
because both the final model file and the resumable Hugging Face cache may
exist simultaneously.

## Clone the repository

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
~~~

## Validate without modifying the system

~~~bash
./scripts/install.sh --validate-only
~~~

Do not continue until the preflight reports:

~~~text
Errors:   0
Warnings: 0
INSTALLATION PREFLIGHT PASSED
~~~

## Install

~~~bash
sudo ./scripts/install.sh
~~~

The installer performs these stages:

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

## Prepare without starting services

~~~bash
sudo ./scripts/install.sh --prepare-only
~~~

## Infrastructure-only testing

The following option skips model checks:

~~~bash
sudo ./scripts/install.sh --skip-model-check
~~~

Use it only for infrastructure troubleshooting. A normal runtime cannot pass
the final verification without the required local models.

## Verify after installation

~~~bash
cd /opt/ai-station
./scripts/verify.sh
~~~

Expected services include:

- Open WebUI;
- UI Gateway;
- Apache Tika;
- SearXNG;
- embedding server;
- general model server;
- Persian OCR;
- local Whisper large-v3.

## Install the complete model profile

~~~bash
cd /opt/ai-station
./scripts/provision-models.sh --profile all
./scripts/verify-models.sh --profile all
~~~

## Upgrade

From the installation directory:

~~~bash
cd /opt/ai-station
git pull --ff-only
sudo ./scripts/install.sh
~~~

When an existing application directory is replaced, the installer creates a
timestamped backup under:

~~~text
/srv/ai-station/backups
~~~

The local `.env` file is preserved.

## Clean-machine acceptance

Before using the project for unattended deployment:

1. test installation on a disposable WSL distribution;
2. verify all host gateway services;
3. confirm a full restart survives `wsl --shutdown`;
4. test backup restoration;
5. record the tested Git commit and model manifest checksums.
