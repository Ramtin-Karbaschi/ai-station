# AI Station Architecture

## Design goals

AI Station is designed around six constraints:

1. inference and document processing remain local;
2. heavy models are stored outside the source repository;
3. container and model versions are reproducible;
4. services are exposed only on loopback by default;
5. operational state can be verified through deterministic checks;
6. multiple application projects share one GenAI platform via a stable API.

The privileged operator console is the `ai` CLI and, on Windows, the
Manager panel that invokes it. Workload UIs (Open WebUI, LiteLLM Admin,
ComfyUI, Graphify map) do not start or stop GPU providers. See
[ADR-016](adr/ADR-016-operator-console-and-selectable-outputs.md).

See also [PLATFORM.md](PLATFORM.md) for the multi-project control plane.

## Logical architecture

~~~mermaid
flowchart TB
    subgraph Host["Linux or Windows 11 / WSL2 host"]
        Browser["Browser"]
        Apps["Application projects"]
        UIGateway["UI Gateway :8890"]
        Gateway["Host Gateway :8888"]
    end

    subgraph Docker["Docker Compose"]
        WebUI["Open WebUI :3000"]
        LiteLLM["LiteLLM Gateway :4000"]
        LLM["llama.cpp heavy profile"]
        Embedder["llama.cpp Embeddings :8090"]
        Reranker["llama.cpp Reranker :8091"]
        Tika["Apache Tika + Tesseract :9998"]
        Search["SearXNG :8889"]
        Postgres["PostgreSQL + pgvector :5432"]
        Redis["Redis :6379"]
        N8N["n8n optional :5678"]
    end

    subgraph Storage["Persistent storage"]
        Models["/srv/ai-station/models"]
        Runtime["/srv/ai-station/runtime"]
        Backups["/srv/ai-station/backups"]
        Volumes["Docker volumes"]
    end

    Browser --> WebUI
    Browser --> N8N
    WebUI --> UIGateway
    UIGateway --> Gateway
    Gateway --> LLM
    Apps --> LiteLLM
    N8N --> LiteLLM
    N8N --> Tika
    LiteLLM --> Gateway
    LiteLLM --> Embedder

    WebUI --> Embedder
    WebUI --> Reranker
    WebUI --> Tika
    WebUI --> Search
    WebUI --> Postgres
    WebUI --> Redis

    LLM --> Models
    Embedder --> Models
    Reranker --> Models
    Postgres --> Volumes
    Redis --> Volumes
    Volumes --> Backups
    LiteLLM --> Runtime
~~~

## Request flow

### Application chat / completion

1. A project sends an OpenAI-compatible request to LiteLLM on `:4000`.
2. LiteLLM authenticates the project virtual key and enforces model allowlists.
3. The project requests a canonical public model name from LiteLLM, such as
   `Qwen3.8-27B-UD-Q4_K_M` or `Ornith-1.5-35B-Q4_K_M`.
4. LiteLLM forwards heavy chat and vision requests to the host gateway, which
   auto-switches the matching heavy runtime when needed.
5. Only one heavy profile is loaded on the GPU at a time.

### Human chat (Open WebUI)

1. The user sends a request through Open WebUI.
2. Open WebUI calls the UI Gateway for OCR-aware attachment handling.
3. The host gateway exposes the OpenAI-compatible endpoint used by the UI path.
4. The gateway selects the requested canonical public model name and routes it
   to the matching llama.cpp runtime, auto-switching heavy profiles when
   needed.

### Retrieval-augmented generation

1. A document is uploaded to Open WebUI.
2. Apache Tika extracts text and performs OCR where required.
3. The local embedding service creates 4096-d vectors (Qwen3 Embedding 8B).
4. Vectors and metadata are stored in PostgreSQL/pgvector. Do not mix with
   leftover 1024-d rows from the retired 0.6B embedder.
5. Hybrid BM25 + vector search selects candidates; the CPU reranker keeps
   the top 3 chunks for the local model context. The live 4B QuantFactory
   GGUF has not passed a ranking-quality check.

Operator notebooks live in Open WebUI Knowledge. See
[clients/OPENWEBUI.md](clients/OPENWEBUI.md). `ai projects` is only the
application API key plane.

### Web search

1. Open WebUI generates or receives a search query.
2. The request is sent to the local SearXNG service.
3. Selected results are injected into the model context.
4. Search traffic leaves the workstation only when the selected upstream
   search engines are queried.

## Service boundaries

| Boundary | Policy |
|---|---|
| Browser to Open WebUI | Localhost HTTP |
| Applications to LiteLLM | Localhost `:4000` or Docker network `ai-platform` |
| Open WebUI to UI gateway | Docker host gateway |
| Container-to-container | Compose network + external `ai-platform` |
| Host service exposure | Application listeners use `127.0.0.1`; the host gateway may mirror onto the exact private `docker0` address for container access, never a wildcard or LAN bind |
| Model storage | Read-only bind mount where possible |
| Secrets | Local `.env`, `secrets/`, and `projects/*.env` |
| Internet | Required only for provisioning and optional web search |

## Persistence

Persistent information is divided into:

- Docker volumes for PostgreSQL, Redis and Open WebUI state;
- `/srv/ai-station/models` for model binaries;
- `/srv/ai-station/runtime` for active heavy-profile state, Graphify
  graphs, operator output prefs, ComfyUI media, and n8n SQLite;
- `/srv/ai-station/backups` for timestamped backups;
- `/opt/ai-station` for version-controlled application files.

Runtime data must not be committed to Git.

## Runtime boundary

Docker Compose is the only supported runtime on native Linux and on
Windows 11 + WSL2. The station is **one Compose project** (`ai-station`).
`ai start` is the operator entry for that unit. llama.cpp heavy
profiles are the same project with Compose profiles. ComfyUI is the
same project plus its overlay file. Engines stay in separate
containers; they are not merged into one image.

The client contract remains independent of container internals:
applications call LiteLLM on `:4000/v1`, and llama.cpp remains the
inference core.

Retained media generation uses a GPU-exclusive ComfyUI overlay on
`127.0.0.1:8188` (ADR-015, [clients/COMFYUI.md](clients/COMFYUI.md)).
It is a different workload from chat and must never be deleted.
`ai start` does not launch it. Starting it stops the active llama.cpp
heavy profile.

Optional n8n automation is a CPU Compose profile on
`127.0.0.1:5678` (ADR-021, [clients/N8N.md](clients/N8N.md)). It is a
different workload from chat, coding, and media. `ai start` does not
launch it. Starting it does not stop llama.cpp. Workflows call LiteLLM
on `:4000/v1` only.

## Reproducibility controls

### Container images

Registry images are pinned in:

~~~text
compose.images.lock.yaml
~~~

Repository-controlled images are built from pinned Dockerfile base images.

### Models

The model manifest defines:

- repository;
- immutable revision;
- source filename;
- destination;
- size;
- SHA-256 checksum;
- installation profile.

The model registry (`config/registry/models.yaml`) defines stable aliases used
by applications.

### Release audit

The release audit verifies:

- Compose validity;
- active service health;
- OCR and Whisper readiness;
- Git ignore rules;
- absence of model binaries;
- file-size limits;
- image locks;
- Dockerfile locks;
- installer validity;
- documentation quality;
- model manifest validity.
