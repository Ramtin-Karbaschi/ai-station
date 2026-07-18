<div align="center">

<img src="docs/assets/ai-station-banner.svg"
     alt="AI Station — local-first AI workstation"
     width="100%">

<br>

[![Documentation](https://github.com/Ramtin-Karbaschi/ai-station/actions/workflows/docs-quality.yml/badge.svg)](https://github.com/Ramtin-Karbaschi/ai-station/actions/workflows/docs-quality.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-2563eb.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-WSL2%20%7C%20Linux-0f766e.svg)
![Runtime](https://img.shields.io/badge/runtime-Docker%20Compose-2496ed.svg)
![GPU](https://img.shields.io/badge/GPU-NVIDIA-76b900.svg)
![Privacy](https://img.shields.io/badge/inference-local--first-7c3aed.svg)

**A reproducible local AI workstation for private LLM inference, document
understanding, search, retrieval and speech recognition.**

[Quick start](#quick-start) ·
[Architecture](#architecture) ·
[Documentation](#documentation) ·
[فارسی](docs/README_FA.md)

</div>

---

## Overview

AI Station is a production-oriented local AI foundation designed primarily
for **Windows 11 + WSL2 + NVIDIA GPUs**.

It combines a browser-based interface, OpenAI-compatible local inference,
document extraction, Persian OCR, local web search, embeddings, vector
storage and speech recognition in one controlled environment.

The project prioritizes:

- local data processing;
- reproducible container and model versions;
- explicit operational scripts;
- localhost-only service exposure;
- separation of source code from large models and runtime data;
- deterministic release validation.

> AI Station is not a public cloud service or a generic collection of every
> available AI tool. It is a deliberately constrained local workstation
> foundation.

## Current status

| Area | Status |
|---|---|
| Primary platform | Windows 11 with WSL2 |
| Linux runtime | Ubuntu-based WSL distribution |
| GPU path | NVIDIA CUDA through Docker |
| Main UI | Open WebUI |
| Default LLM | Qwen3.6 35B-A3B GGUF |
| Embeddings | Qwen3 Embedding 0.6B |
| Document extraction | Apache Tika |
| Persian OCR | Tesseract `fas` language pack |
| Web search | SearXNG |
| Speech recognition | Local faster-whisper large-v3 |
| Release maturity | Production-oriented technical preview |

The current runtime has passed the repository release audit with:

~~~text
Errors:   0
Warnings: 0
~~~

## Main capabilities

| Capability | Implementation |
|---|---|
| Local chat interface | Open WebUI |
| OpenAI-compatible inference | AI Station gateway + llama.cpp server |
| GPU inference | NVIDIA CUDA container runtime |
| Retrieval-augmented generation | Open WebUI RAG + local embeddings |
| Vector persistence | PostgreSQL + pgvector |
| Cache and WebSockets | Redis |
| Document parsing | Apache Tika |
| Persian and English OCR | Tesseract through Tika |
| Local search | SearXNG |
| Speech-to-text | faster-whisper large-v3 |
| Reproducible containers | SHA-256 image digests |
| Reproducible models | Immutable revisions and SHA-256 checksums |

## Architecture

~~~mermaid
flowchart LR
    U[User] --> W[Open WebUI<br/>127.0.0.1:3000]

    W --> UI[UI Gateway<br/>127.0.0.1:8890]
    UI --> G[AI Station Gateway<br/>127.0.0.1:8888]
    G --> L[llama.cpp General LLM<br/>127.0.0.1:8082]

    W --> E[Embedding Server<br/>127.0.0.1:8090]
    W --> T[Apache Tika + Persian OCR<br/>127.0.0.1:9998]
    W --> S[SearXNG<br/>127.0.0.1:8889]
    W --> P[(PostgreSQL + pgvector)]
    W --> R[(Redis)]
    W --> STT[Local Whisper Cache]

    L --> M[/srv/ai-station/models]
    E --> M
    STT --> D[/srv/ai-station runtime data]
    P --> D
    R --> D
~~~

The application and persistent data are intentionally separated:

~~~text
/opt/ai-station          Application, configuration and scripts
/srv/ai-station          Models, caches, backups and runtime data
~~~

See [Architecture](docs/ARCHITECTURE.md) for the detailed request flow,
trust boundaries and persistence model.

## Requirements

### Host requirements

- Windows 11 with WSL2, or a compatible Ubuntu-based Linux host;
- Docker Engine or Docker Desktop with Docker Compose v2;
- an NVIDIA GPU visible from WSL/Linux through `nvidia-smi`;
- Git, Python 3, OpenSSL, curl and rsync;
- internet access during initial image and model provisioning.

### Recommended baseline for the default model

| Resource | Recommendation |
|---|---|
| GPU VRAM | Approximately 24 GB |
| System RAM | 64 GB |
| Free storage | At least 80 GiB |
| Storage type | SSD or NVMe |
| CPU | Modern 8-core or better |

Lower-resource systems require replacing the default GGUF model and adjusting
the context and GPU-layer settings.

## Quick start

### 1. Clone

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
~~~

### 2. Validate the host

~~~bash
./scripts/install.sh --validate-only
~~~

### 3. Install

~~~bash
sudo ./scripts/install.sh
~~~

The installer validates the host, creates the supported directory layout,
generates local configuration, pulls digest-pinned images, builds the local
Tika image, provisions the Core model profile and performs health checks.

### 4. Open the interface

~~~text
http://127.0.0.1:3000
~~~

The first user registered in Open WebUI becomes the local administrator.

## Model profiles

| Profile | Included roles | Approximate purpose |
|---|---|---|
| `core` | General reasoning + embedding | Default operation |
| `all` | Core + coding + reranking | Complete downloaded model pack |

Install or verify models:

~~~bash
./scripts/provision-models.sh --profile core
./scripts/verify-models.sh --profile core

./scripts/provision-models.sh --profile all
./scripts/verify-models.sh --profile all
~~~

Model binaries are not stored in Git. Their repositories, immutable revisions,
sizes and SHA-256 checksums are defined in
[`config/model-manifest.json`](config/model-manifest.json).

## Common operations

~~~bash
make help
make start
make status
make verify
make logs
make stop
make audit
~~~

Equivalent scripts are available under [`scripts/`](scripts/).

## Local endpoints

All default host ports bind to `127.0.0.1`.

| Service | Default endpoint |
|---|---|
| Open WebUI | `http://127.0.0.1:3000` |
| AI Station Gateway | `http://127.0.0.1:8888` |
| UI Gateway | `http://127.0.0.1:8890` |
| SearXNG | `http://127.0.0.1:8889` |
| General LLM | `http://127.0.0.1:8082/v1` |
| Embedding API | `http://127.0.0.1:8090/v1` |
| Apache Tika | `http://127.0.0.1:9998` |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

Do not expose these ports directly to the public internet.

## Reproducibility

AI Station uses several independent controls:

1. Registry images are pinned by immutable digest.
2. Dockerfile base images are pinned by immutable digest.
3. Local images are built from repository-controlled Dockerfiles.
4. Model downloads use immutable Hugging Face revisions.
5. Model files are verified using size and SHA-256.
6. A release audit checks runtime health and repository hygiene.

Run:

~~~bash
./scripts/release-audit.sh
~~~

## Security

- Runtime endpoints bind to loopback by default.
- Real `.env` files, secrets, models, databases and backups are excluded from
  Git.
- Open WebUI authentication is enabled.
- Models and images are cryptographically pinned.
- The default configuration is intended for a trusted local workstation.

For vulnerability reporting, read [SECURITY.md](SECURITY.md). Do not report
security vulnerabilities through a public issue.

## Support matrix

| Environment | Support level |
|---|---|
| Windows 11 + WSL2 + NVIDIA | Validated primary platform |
| Native Ubuntu + NVIDIA | Best effort |
| Native Windows without WSL2 | Not supported |
| CPU-only inference | Not supported by the default profile |
| AMD GPU inference | Not currently validated |
| Direct internet exposure | Unsupported |
| Multi-node deployment | Outside the current scope |

A fresh-machine acceptance test is still recommended before using the
installer for unattended or organizational deployment.

## Documentation

| Document | Purpose |
|---|---|
| [Installation](docs/INSTALLATION.md) | Beginner-friendly installation and upgrade |
| [Architecture](docs/ARCHITECTURE.md) | Components, flows and trust boundaries |
| [Operations](docs/OPERATIONS.md) | Start, stop, status, logs and validation |
| [Models](docs/MODELS.md) | Profiles, downloads and checksum policy |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common failure diagnosis |
| [Image lock](docs/IMAGE_LOCK.md) | Container reproducibility policy |
| [Portability](docs/PORTABILITY_POLICY.md) | Supported paths and repository rules |
| [Current state](docs/ops/AI_STATION_CURRENT_STATE.md) | Verified runtime baseline |
| [راهنمای فارسی](docs/README_FA.md) | معرفی و شروع سریع فارسی |

## Project scope

Included:

- local inference and embeddings;
- local document and OCR processing;
- local RAG and vector persistence;
- local web search integration;
- local speech recognition;
- installation, verification and operational tooling.

Not currently included:

- public SaaS deployment;
- Kubernetes;
- distributed inference;
- cloud inference APIs;
- automatic model training;
- unrestricted internet-facing access;
- guaranteed support for arbitrary hardware.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before creating an issue or pull
request.

## License

AI Station source code and project documentation are licensed under the
[MIT License](LICENSE).

Copyright © 2026 **Ramtin Karbaschi**.

Third-party containers, libraries and models retain their own licenses and
terms. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

<div align="center">

Built as a serious local AI foundation—not as a collection of overlapping
tools.

</div>
