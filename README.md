# AI Station

AI Station is a local-first AI workstation foundation for Windows 11,
WSL2 and NVIDIA GPUs.

## Main capabilities

- OpenAI-compatible local LLM inference
- local embeddings and retrieval
- Open WebUI
- SearXNG local web search
- Apache Tika document extraction
- Persian OCR language support
- local Whisper large-v3 speech recognition
- PostgreSQL with pgvector
- Redis
- reproducible Docker and model locks

## Supported layout

Application code:

    /opt/ai-station

Models, caches, backups and runtime data:

    /srv/ai-station

## Clean installation

Clone the repository and execute:

    sudo ./scripts/install.sh

Validate without modifying the system:

    ./scripts/install.sh --validate-only

## Model profiles

Install the default runtime models:

    ./scripts/provision-models.sh --profile core

Install the complete model pack:

    ./scripts/provision-models.sh --profile all

## Verification

Runtime verification:

    ./scripts/verify.sh

Release verification:

    ./scripts/release-audit.sh

A valid release must report:

    Errors:   0
    Warnings: 0

## Interface

Open WebUI:

    http://127.0.0.1:3000

## Security and reproducibility

- Services bind to localhost by default.
- Secrets are excluded from Git.
- Registry images use immutable digests.
- Dockerfile base images use immutable digests.
- Model downloads use immutable revisions and SHA-256 checksums.
- Runtime data remains outside the repository.
