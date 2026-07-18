# Model Management

AI Station does not commit model binaries to Git.

The authoritative model definition is:

~~~text
config/model-manifest.json
~~~

## Manifest fields

Each model entry contains:

| Field | Meaning |
|---|---|
| `id` | Stable AI Station identifier |
| `role` | General, coding, embedding or reranking role |
| `repo_id` | Hugging Face repository |
| `filename` | Exact upstream filename |
| `revision` | Immutable source commit |
| `destination` | Relative path beneath the data root |
| `size_bytes` | Expected file size |
| `sha256` | Expected SHA-256 checksum |
| `profiles` | Installation profiles containing the model |

## Profiles

### Core

The Core profile provides the default operational models:

- Qwen3.6 35B-A3B general model;
- Qwen3 Embedding 0.6B.

~~~bash
./scripts/provision-models.sh --profile core
./scripts/verify-models.sh --profile core
~~~

### All

The complete profile additionally provisions:

- Qwen3 Coder 30B-A3B;
- Qwen3 Reranker 0.6B.

~~~bash
./scripts/provision-models.sh --profile all
./scripts/verify-models.sh --profile all
~~~

## Resume behavior

The Hugging Face cache is retained at:

~~~text
/srv/ai-station/cache/huggingface
~~~

Interrupted downloads can resume from this cache.

A downloaded file is placed at its final destination only after:

1. its size matches the manifest;
2. its SHA-256 checksum matches the manifest.

Invalid existing files are quarantined rather than silently overwritten.

## Default model paths

~~~text
/srv/ai-station/models/general
/srv/ai-station/models/coder
/srv/ai-station/models/embedding
/srv/ai-station/models/reranker
/srv/ai-station/models/ocr
/srv/ai-station/models/vision
/srv/ai-station/models/whisper
~~~

## VRAM policy

The default general and coding models are heavy models. On a 24 GB GPU, avoid
running multiple heavy models simultaneously.

Stop an unused heavy model before starting another.

## Adding or replacing a model

A model update is incomplete until all of these are updated:

1. model file source;
2. immutable source revision;
3. local destination;
4. expected size;
5. SHA-256 checksum;
6. service command or runtime catalog;
7. documentation;
8. release audit result.

Do not use a mutable branch such as `main` as a production model revision.
