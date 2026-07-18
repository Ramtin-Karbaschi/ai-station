# Docker Image Lock

AI Station separates container images into three categories.

## Registry images

Registry-backed images are pinned using immutable SHA-256 digest references
inside `compose.images.lock.yaml`.

## Repository builds

Services that contain a Compose `build` definition use:

    pull_policy: build

They are built from the source and Dockerfile contained in the repository.

## Local image artifacts

Images created by provisioning scripts but not published to a registry use:

    pull_policy: never

The installer must build or provision those images before starting the
Compose project.

## Updating the lock

Run:

    ./scripts/update-image-lock.sh

Then execute:

    ./scripts/verify-image-lock.sh
    ./scripts/release-audit.sh

The image-lock file must be committed whenever an approved image version
changes.
