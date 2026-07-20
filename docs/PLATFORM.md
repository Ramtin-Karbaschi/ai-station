# AI Station Local GenAI Platform

AI Station is the workstation-local GenAI control plane. Application projects
do not embed or start LLM weights. They call a stable OpenAI-compatible API.

## Architecture

```text
Application A ─┐
Application B ─┼──> LiteLLM Gateway :4000 ──> llama.cpp profile ──> GPU
Application C ─┘            │
                            ├── Virtual API keys (per project)
                            ├── Model aliases (local-*)
                            ├── Usage metrics
                            └── Access policies

Open WebUI :3000 ──> UI Gateway :8890 ──> Host Gateway :8888 ──> active llama.cpp
```

## Always-on services

| Service | Role |
|---|---|
| `llm-gateway` | LiteLLM — project-facing OpenAI API |
| `postgres` | Open WebUI + LiteLLM metadata |
| `redis` | Open WebUI websockets |
| `embedder` | Always-on embeddings |
| `tika` / `searxng` / `open-webui` | Human RAG / chat UI |

## On-demand heavy profiles

Only **one** heavy profile may run on a ~24GB GPU:

| Profile | Alias | Port |
|---|---|---|
| `general` | `local-general` | 8082 |
| `coder` | `local-coder` | 8083 |
| `reasoning` | `local-reasoning` | 8084 |
| `vision` | `local-vision` | 8085 |

Optional: `reranker` (`local-reranker`, port 8091) runs CPU-only so it can
coexist with one heavy GPU model.

## Operator CLI

```bash
ai start --profile general
ai models use coder
ai models active
ai projects create inventory-api --models local-general,local-embedding
ai projects list
ai status
ai verify
```

## Application integration

Host process:

```env
LLM_BASE_URL=http://127.0.0.1:4000/v1
LLM_API_KEY=<from ai projects create>
LLM_MODEL=local-general
```

Docker Compose project:

```yaml
services:
  api:
    environment:
      LLM_BASE_URL: http://llm-gateway:4000/v1
      LLM_API_KEY: ${LLM_API_KEY}
      LLM_MODEL: local-general
    networks:
      - default
      - ai-platform

networks:
  ai-platform:
    external: true
```

Python client (local gateway, not OpenAI cloud):

```python
from openai import OpenAI
import os

client = OpenAI(
    base_url=os.environ["LLM_BASE_URL"],
    api_key=os.environ["LLM_API_KEY"],
    timeout=120.0,
)
```

## Security defaults

- Gateway published on `127.0.0.1:4000` only
- Runtime model ports published on loopback for host tooling; apps should use the gateway
- Per-project virtual keys; master key stays in `.env`
- Message body logging disabled in LiteLLM (`turn_off_message_logging`)
- Response cache disabled
- No cloud providers configured in the gateway
- Model mounts are read-only
- Project credential files under `projects/*.env` are gitignored

## Registries

| File | Purpose |
|---|---|
| `config/registry/models.yaml` | Canonical aliases, profiles, files |
| `config/registry/projects.yaml` | Project inventory (no secrets) |
| `config/model-catalog.json` | Host gateway selectable models |
| `config/model-manifest.json` | Provisioning checksums |
| `config/gateway/litellm.yaml` | LiteLLM routes |

## Path contract

| Path | Role |
|---|---|
| `/opt/ai-station` | Version-controlled platform |
| `/srv/ai-station/models` | Model binaries |
| `/srv/ai-station/runtime` | Active profile state |
| `/opt/ai-station/projects` | Per-project env secrets |
