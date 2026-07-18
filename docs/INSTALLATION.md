# AI Station Installation

AI Station uses two host paths:

- Application: `/opt/ai-station`
- Persistent data: `/srv/ai-station`

The repository may be cloned anywhere. The installer deploys the application
to the supported application root and keeps models, backups and runtime data
outside Git.

## Requirements

- Linux or WSL2
- Docker Engine or Docker Desktop with Linux-container integration
- Docker Compose v2
- NVIDIA GPU visibility through `nvidia-smi`
- At least 80 GiB of free storage for the current model pack
- Git, OpenSSL, Python 3 and rsync

## Preflight

Run:

    ./scripts/preflight-install.sh

## Validate the installer

Run:

    ./scripts/install.sh --validate-only

## Install

Run:

    sudo ./scripts/install.sh

## Prepare without starting services

Run:

    sudo ./scripts/install.sh --prepare-only

## Model artifacts

The installer verifies every model file referenced by Docker Compose.

Model binaries are intentionally excluded from Git. They must be provisioned
under `/srv/ai-station/models` before the services are started.

The model provisioning workflow is maintained separately from infrastructure
installation so large model downloads can be resumed and verified by checksum.

## Upgrade behavior

When the target application directory already exists, the installer creates
a timestamped backup under `/srv/ai-station/backups` before deploying the new
repository files.

The existing `.env` file is preserved.
