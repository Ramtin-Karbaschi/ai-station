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
| `embedder` | Always-on CPU embeddings (ADR-022) |
| `reranker` | Always-on CPU rerank for Open WebUI hybrid RAG |
| `tika` / `searxng` / `open-webui` | Human RAG / chat UI |

## On-demand heavy profiles

Only **one** heavy profile may run on a ~24GB GPU:

| Profile | Canonical model name | Port |
|---|---|---|
| `general` | `Qwen3.8-27B-UD-Q4_K_M` | 8082 |
| `coder` | `Ornith-1.5-35B-Q4_K_M` | 8083 |
| `reasoning` | `Qwen3.8-27B-Reasoning-UD-Q4_K_M` | 8084 |
| `vision` | `Qwen3.8-27B-Vision-UD-Q4_K_M` | 8085 |
| `ornith` (retained) | `Ornith-1.5-35B-Q4_K_M` | 8086 |
| `qwen38` (retained) | `Qwen3.8-27B-UD-Q4_K_M` | 8087 |
| `longwriter` (retained) | `LongWriter-Zero-32B-Q4_K_M` | 8088 |

`ornith` does not replace `coder` (ADR-008). `qwen38` does not replace
`general` or `vision` (ADR-019). `longwriter` does not replace `general`
or `reasoning` (ADR-020). Rollback is `ai models use general`.

The CPU reranker (`Qwen3-Reranker-4B-Q6_K`, port 8091) starts with
`ai start` and can coexist with one heavy GPU model.

## Operator CLI

```bash
ai start --profile general
ai models use coder
ai models active
ai projects create inventory-api --models Qwen3.8-27B-UD-Q4_K_M,Qwen3-Embedding-8B-Q4_K_M
ai projects list
ai opencode configure
ai opencode test
ai graphify view
ai output show
ai status
ai verify
```

## Use cases

### 1) Document Q&A / decision support (RAG)

LiteLLM only provides API keys and model routing. Document upload, OCR, and
retrieval live in your application or in Open WebUI:

- **Interactive / human:** Open WebUI at `http://127.0.0.1:3000`. Create a
  Knowledge collection (one notebook per topic), upload sources, attach
  that collection to a chat. That is **not** `ai projects`. See
  [clients/OPENWEBUI.md](clients/OPENWEBUI.md).
- **Programmatic:** create a project key that allows
  `Qwen3.8-27B-UD-Q4_K_M` + `Qwen3-Embedding-8B-Q4_K_M`, store chunks in
  your DB/pgvector, then call chat with
  retrieved context.

### 2) Automation agents (email triage, tools, workflows)

Optional visual path: n8n on `http://127.0.0.1:5678` (off by default).
See [clients/N8N.md](clients/N8N.md). Workflows call LiteLLM at
`http://llm-gateway:4000/v1` with the `n8n` project key
(`ai n8n configure`). IMAP/Gmail credentials stay in n8n, not in Git.

You can still build the agent in your own project (Python/Node). Give it
a dedicated LiteLLM virtual key with only the models it needs (usually
`Qwen3.8-27B-UD-Q4_K_M` or `Ornith-1.5-35B-Q4_K_M`). The
agent code owns Gmail/IMAP credentials and tool actions; the gateway
only serves model inference.

Recommended pattern: one virtual key per use-case / project.

```text
docs-rag-api      -> models: Qwen3.8-27B-UD-Q4_K_M, Qwen3-Embedding-8B-Q4_K_M
email-agent-api   -> models: Qwen3.8-27B-UD-Q4_K_M
n8n               -> models: Qwen3.8-27B-UD-Q4_K_M, Ornith-1.5-35B-Q4_K_M, Qwen3-Embedding-8B-Q4_K_M
coder-agent-api   -> models: Ornith-1.5-35B-Q4_K_M
opencode          -> models: Ornith-1.5-35B-Q4_K_M, Qwen3.8-27B-UD-Q4_K_M, Qwen3.8-27B-Reasoning-UD-Q4_K_M
```

### 3) OpenCode developer runtime (WSL)

OpenCode is a first-class LiteLLM client and runs inside WSL as the dedicated
non-root user `aidev`. Point it at
`http://127.0.0.1:4000/v1` with the `opencode` project key. One provider
`ai-station` lists three tool-capable models (Ornith/coder, Qwen3.8, and
the same Ornith bytes on the compatibility profile) plus Qwen3.8 Reasoning.
Default `model`/`small_model` is `Ornith-1.5-35B-Q4_K_M`. Title/summary
agents are disabled so they cannot GPU-swap. `ai opencode use <profile>`
warms that GPU and aligns `model`/`small_model` without hiding the picker.
Advertised OpenCode context for Qwen3.8 is **262144** after the 2026-08-27
probe (Q4 KV, flash-attn, 138801-token ingest). Ornith/coder stay at
**8192**. The build agent has LSP,
formatter, skills, edit/Bash access
inside the worktree, and 40 iterations. Native compaction is enabled; the
custom continuation hook is not part of the system.

~~~bash
ai opencode install --create-user --own-project
ai opencode configure
ai opencode doctor
ai opencode acceptance
ai opencode run /opt/ai-station
~~~

The live acceptance must prove tool use, a file edit, and a passing test.
Windows Manager option 28 launches the same WSL-native client. Details:
[clients/OPENCODE.md](clients/OPENCODE.md). ADR:
[ADR-009](adr/ADR-009-opencode-local-client.md).

## LiteLLM Admin UI login

Open `http://127.0.0.1:4000/ui`

Credentials are stored locally in:

```text
/opt/ai-station/secrets/litellm_ui_credentials.txt
```

Or from Windows Manager: option **27. Show LiteLLM UI login**.

Default username is `admin`. This is separate from Open WebUI login.

Host process:

```env
LLM_BASE_URL=http://127.0.0.1:4000/v1
LLM_API_KEY=<from ai projects create>
LLM_MODEL=Qwen3.8-27B-UD-Q4_K_M
```

Docker Compose project:

```yaml
services:
  api:
    environment:
      LLM_BASE_URL: http://llm-gateway:4000/v1
      LLM_API_KEY: ${LLM_API_KEY}
      LLM_MODEL: Qwen3.8-27B-UD-Q4_K_M
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
| `config/providers.yaml` | Provider lifecycle, admission budgets, Compose overlays |
| `config/registry/models.yaml` | Canonical aliases, profiles, files |
| `config/registry/projects.yaml` | Project inventory (no secrets) |
| `config/model-catalog.json` | Host gateway selectable models |
| `config/model-manifest.json` | Provisioning checksums |
| `config/gateway/litellm.yaml` | LiteLLM routes |

Admission dry-run:

~~~bash
ai provider list
ai provider start llama-cpp-general --dry-run
~~~

## Path contract

| Path | Role |
|---|---|
| `/opt/ai-station` | Version-controlled platform |
| `/srv/ai-station/models` | Model binaries |
| `/srv/ai-station/runtime` | Active profile state |
| `/opt/ai-station/projects` | Per-project env secrets |
