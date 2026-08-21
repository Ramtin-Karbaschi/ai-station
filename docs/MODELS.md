# Model Management

AI Station does not commit model binaries to Git.

The operator's remaining product choice is which local model fits this
machine's VRAM, RAM, and disk. Bytes live under `/srv/ai-station`.

The authoritative model definition is:

~~~text
config/model-manifest.json
~~~

Runtime catalog and provider lifecycle:

~~~text
config/model-catalog.json
config/providers.yaml
~~~

## Hardware guidance

On a single GPU, run **at most one** heavy profile at a time. These numbers
are planning hints, not guarantees:

| VRAM (approx.) | Start with |
|---|---|
| ≥ 22 GiB | Core `general` (Qwen3.6 35B-A3B Q4) plus embeddings |
| ≥ 18 GiB | `coder` (Qwen3 Coder 30B-A3B Q4) for OpenCode |
| ≥ 16 GiB | A smaller Q4 GGUF registered with `ai models add` |
| < 16 GiB | Do not expect the default 30–35B Q4 pack to fit |

Confirm with `nvidia-smi` and `ai provider start <id> --dry-run` before
downloading a multi-gigabyte file.

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
make models-core
~~~

### All

Core plus selectable heavy and optional roles:

- Qwen3 Coder 30B-A3B;
- DeepSeek-R1 Distill Qwen 32B (reasoning);
- Qwen3-VL 32B + mmproj (vision);
- Ornith-1.0 35B Q4 (optional coding profile; does not replace coder);
- Qwen3 Reranker 0.6B (optional CPU).

~~~bash
./scripts/provision-models.sh --profile all
./scripts/verify-models.sh --profile all
~~~

Experimental SGLang AWQ shards may appear in the manifest under
`experimental-sglang` for research. They are **not** part of production
provisioning and are not promoted (see ADR-002).

## Day-to-day add and remove

~~~bash
ai models catalog
ai models catalog --json
ai models add coder-qwen3-30b-a3b-q4
ai models install coder-qwen3-30b-a3b-q4
ai models verify coder-qwen3-30b-a3b-q4
ai models remove coder-qwen3-30b-a3b-q4              # dry-run
ai models remove coder-qwen3-30b-a3b-q4 --confirm    # quarantine, not deletion
ai models restore coder-qwen3-30b-a3b-q4 --confirm
~~~

`ai models add <manifest-id>` installs a curated id. `remove` refuses the
active heavy profile. Required core models also require `--allow-required`.
Quarantined files live under `/srv/ai-station/quarantine/models/`.

Windows Manager exposes Catalog, Install, Add, Remove, and Restore.

## Register a new Hugging Face GGUF

Do not use a mutable branch such as `main` as a production revision.

~~~bash
ai models add \
  --id my-model-q4 \
  --repo org/name \
  --filename model.gguf \
  --role general \
  --revision 0123456789abcdef0123456789abcdef01234567

# When size and sha256 are known:
ai models add ... --sha256 <64-hex> --size-bytes N --confirm
ai models install my-model-q4
~~~

A model is not a runtime profile until catalog, providers, and LiteLLM
routing are updated. The `add --confirm` command prints that next step.

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
/srv/ai-station/models/ornith
/srv/ai-station/models/thinking
/srv/ai-station/models/vision
/srv/ai-station/models/embedding
/srv/ai-station/models/reranker
/srv/ai-station/models/whisper
/srv/ai-station/models/custom
~~~

## Runtime profile switch

~~~bash
ai models use general
ai models use coder
ai models use ornith
ai models stop
~~~

Admission dry-run:

~~~bash
ai provider start llama-cpp-coder --dry-run
ai provider start llama-cpp-ornith --dry-run
~~~

`ornith` is an optional heavy profile (ADR-008). It does not replace
`coder`. Rollback is `ai models use general`.
