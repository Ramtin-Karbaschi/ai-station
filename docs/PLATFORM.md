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
| `reranker` | Always-on CPU rerank for Open WebUI hybrid RAG |
| `tika` / `searxng` / `open-webui` | Human RAG / chat UI |

## On-demand heavy profiles

Only **one** heavy profile may run on a ~24GB GPU:

| Profile | Canonical model name | Port |
|---|---|---|
| `general` | `Qwen3.6-35B-A3B-UD-Q4_K_M` | 8082 |
| `coder` | `Qwen3-Coder-30B-A3B-Instruct-Q4` | 8083 |
| `reasoning` | `DeepSeek-R1-Distill-Qwen-32B-Q4_K_M` | 8084 |
| `vision` | `Qwen3-VL-32B-Instruct-Q4_K_M` | 8085 |
| `ornith` (optional) | `Ornith-1.0-35B-Q4_K_M` | 8086 |

`ornith` does not replace `coder` (ADR-008). Rollback is `ai models use general`.

The CPU reranker (`Qwen3-Reranker-0.6B-Q8_0`, port 8091) starts with
`ai start` and can coexist with one heavy GPU model.

## Operator CLI

```bash
ai start --profile general
ai models use coder
ai models active
ai projects create inventory-api --models Qwen3.6-35B-A3B-UD-Q4_K_M,Qwen3-Embedding-0.6B-Q8_0
ai projects list
ai opencode configure
ai opencode test
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
  `Qwen3.6-35B-A3B-UD-Q4_K_M` + `Qwen3-Embedding-0.6B-Q8_0`, store chunks in
  your DB/pgvector, then call chat with
  retrieved context.

### 2) Automation agents (email triage, tools, workflows)

Build the agent in your own project (Python/Node). Give it a dedicated LiteLLM
virtual key with only the models it needs (usually
`Qwen3.6-35B-A3B-UD-Q4_K_M` or `Qwen3-Coder-30B-A3B-Instruct-Q4`). The agent
code owns Gmail/IMAP credentials and tool actions; the gateway only serves
model inference.

Recommended pattern: one virtual key per use-case / project.

```text
docs-rag-api      -> models: Qwen3.6-35B-A3B-UD-Q4_K_M, Qwen3-Embedding-0.6B-Q8_0
email-agent-api   -> models: Qwen3.6-35B-A3B-UD-Q4_K_M
coder-agent-api   -> models: Qwen3-Coder-30B-A3B-Instruct-Q4
opencode          -> models: Qwen3-Coder-30B-A3B-Instruct-Q4, Qwen3.6-35B-A3B-UD-Q4_K_M, DeepSeek-R1-Distill-Qwen-32B-Q4_K_M, Ornith-1.0-35B-Q4_K_M
```

### 3) OpenCode developer runtime (WSL)

OpenCode is a first-class LiteLLM client and runs inside WSL as the dedicated
non-root user `aidev`. Point it at
`http://127.0.0.1:4000/v1` with the `opencode` project key. One provider
`ai-station` lists three tool-capable models (Coder, Qwen3.6, Ornith) plus
DeepSeek for non-tool reasoning. Default `model`/`small_model` is
`Qwen3-Coder-30B-A3B-Instruct-Q4`. Title/summary agents are disabled so they
cannot GPU-swap. `ai opencode use <profile>` warms that
GPU and aligns `model`/`small_model` without hiding the picker. Coder
remains the station default (ADR-008). The shared coder runtime ceiling is
32768, while OpenCode deliberately advertises a verified 16384 client limit;
the other profiles are 8192. The build agent has LSP,
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
LLM_MODEL=Qwen3.6-35B-A3B-UD-Q4_K_M
```

Docker Compose project:

```yaml
services:
  api:
    environment:
      LLM_BASE_URL: http://llm-gateway:4000/v1
      LLM_API_KEY: ${LLM_API_KEY}
      LLM_MODEL: Qwen3.6-35B-A3B-UD-Q4_K_M
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
