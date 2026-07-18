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

The current local build is the Persian-enabled Apache Tika image.

## Updating the lock

After an approved container update:

~~~bash
./scripts/update-image-lock.sh
./scripts/verify-image-lock.sh
./scripts/verify-build-lock.sh
./scripts/release-audit.sh
~~~

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
