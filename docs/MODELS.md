# AI Station Model Provisioning

Model binaries are not stored in Git.

The committed model definition is:

    config/model-manifest.json

Every model entry includes:

- Hugging Face repository
- immutable source revision
- exact source filename
- destination beneath the persistent data root
- expected file size
- SHA-256 checksum
- installation profiles

## Core profile

The Core profile installs the default runtime models:

- general reasoning model
- embedding model

Install or verify it with:

    ./scripts/provision-models.sh --profile core
    ./scripts/verify-models.sh --profile core

## Complete profile

The Complete profile additionally installs:

- coding model
- reranker model

Install or verify it with:

    ./scripts/provision-models.sh --profile all
    ./scripts/verify-models.sh --profile all

The download cache is retained under:

    /srv/ai-station/cache/huggingface

A model is moved into its final destination only after its size and
SHA-256 checksum match the committed manifest.
