# Docker Image Lock

AI Station separates Docker images into two active categories.

## Registry images

Registry images are pinned to immutable SHA-256 digests in:

~~~text
compose.images.lock.yaml
~~~

A tag such as `latest` or `7-alpine` is human-readable but mutable. The lock
file determines the exact content used by the validated release.

## Repository builds

Images built from project-controlled Dockerfiles use:

~~~yaml
pull_policy: build
~~~

Their upstream `FROM` images are independently pinned by digest and recorded
in:

~~~text
config/dockerfile-base-lock.json
~~~

The current local builds are the Persian-enabled Apache Tika image,
PaddleOCR-VL-1.6 (`infra/paddleocr-vl/Dockerfile`, Compose profile
`ocr-vl`), and the retained ComfyUI media image
(`infra/comfyui/Dockerfile`). n8n is a registry image
(`docker.n8n.io/n8nio/n8n`) gated by Compose profile `n8n` and pinned in
the same lock file. The n8n sandbox API, cert bootstrap, and privileged
runner images (`ghcr.io/n8n-io/n8n-sandbox-service-*`) are pinned there
too. The inner sandbox image is digest-pinned in Compose env
(`SANDBOX_RUNNER_DOCKER_SANDBOX_IMAGE`).

## Updating the lock

After an approved container update:

~~~bash
./scripts/update-image-lock.sh
./scripts/verify-image-lock.sh --require-local
./scripts/verify-build-lock.sh
./scripts/release-audit.sh
~~~

Offline quality (`make check`) runs `verify-image-lock.sh`
without `--require-local` so a clone can prove digest pins without downloading
GPU images. After `docker compose pull`, use `--require-local`.

Commit these files together when applicable:

- `compose.images.lock.yaml`;
- `config/image-lock.json`;
- `config/image-lock-summary.txt`;
- Dockerfile changes;
- `config/dockerfile-base-lock.json`.

## Prohibited release state

A release must not be accepted when:

- a registry service lacks a digest;
- a Dockerfile base image lacks a digest;
- a local image cannot be reproduced from the repository;
- the resolved Compose configuration differs from the committed lock;
- the release audit reports a warning or error.
