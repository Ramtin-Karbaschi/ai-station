# Model Management

AI Station does not commit model binaries to Git.

The authoritative model definition is:

~~~text
config/model-manifest.json
~~~

Runtime catalog and provider lifecycle:

~~~text
config/model-catalog.json
config/providers.yaml
~~~

## Manifest fields

Each model entry contains:

| Field | Meaning |
|---|---|
| `id` | Stable AI Station identifier |
| `role` | Operational role |
| `repo_id` | Hugging Face repository |
| `filename` | Exact upstream filename |
| `revision` | Immutable source commit |
| `destination` | Relative path beneath the data root |
| `size_bytes` | Expected file size |
| `sha256` | Expected SHA-256 checksum |
| `profiles` | Installation profiles containing the model |

## Profiles

### Core

Default operational models:

- Qwen3.6 35B-A3B general (GGUF);
- Qwen3 Embedding 0.6B.

~~~bash
./scripts/provision-models.sh --profile core
./scripts/verify-models.sh --profile core
~~~

### All

Core plus selectable heavy and optional roles:

- Qwen3 Coder 30B-A3B;
- DeepSeek-R1 Distill Qwen 32B (reasoning);
- Qwen3-VL 32B + mmproj (vision);
- Qwen3 Reranker 0.6B (optional CPU).

~~~bash
./scripts/provision-models.sh --profile all
./scripts/verify-models.sh --profile all
~~~

Experimental SGLang AWQ shards may appear in the manifest under
`experimental-sglang` for research. They are **not** part of production
provisioning and are not promoted (see ADR-002).

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
/srv/ai-station/models/thinking
/srv/ai-station/models/vision
/srv/ai-station/models/embedding
/srv/ai-station/models/reranker
/srv/ai-station/models/whisper
~~~

## VRAM policy

On a single 24 GB GPU, run **at most one** heavy profile at a time
(`general`, `coder`, `reasoning`, or `vision`). Use:

~~~bash
ai models use general
ai models use coder
ai models stop
~~~

Admission dry-run:

~~~bash
ai provider start llama-cpp-coder --dry-run
~~~

## Adding or replacing a model

A model update is incomplete until all of these are updated:

1. model file source;
2. immutable source revision;
3. local destination;
4. expected size;
5. SHA-256 checksum;
6. service command or runtime catalog / providers registry;
7. documentation;
8. release audit result.

Do not use a mutable branch such as `main` as a production model revision.
