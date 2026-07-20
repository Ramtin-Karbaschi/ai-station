# AI Station Architecture

## Design goals

AI Station is designed around six constraints:

1. inference and document processing remain local;
2. heavy models are stored outside the source repository;
3. container and model versions are reproducible;
4. services are exposed only on loopback by default;
5. operational state can be verified through deterministic checks;
6. multiple application projects share one GenAI platform via a stable API.

See also [PLATFORM.md](PLATFORM.md) for the multi-project control plane.

## Logical architecture

~~~mermaid
flowchart TB
    subgraph Host["Windows 11 / WSL2 host"]
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
        Tika["Apache Tika + Tesseract :9998"]
        Search["SearXNG :8889"]
        Postgres["PostgreSQL + pgvector :5432"]
        Redis["Redis :6379"]
    end

    subgraph Storage["Persistent storage"]
        Models["/srv/ai-station/models"]
        Runtime["/srv/ai-station/runtime"]
        Backups["/srv/ai-station/backups"]
        Volumes["Docker volumes"]
    end

    Browser --> WebUI
    WebUI --> UIGateway
    UIGateway --> Gateway
    Gateway --> LLM
    Apps --> LiteLLM
    LiteLLM --> LLM
    LiteLLM --> Embedder

    WebUI --> Embedder
    WebUI --> Tika
    WebUI --> Search
    WebUI --> Postgres
    WebUI --> Redis

    LLM --> Models
    Embedder --> Models
    Postgres --> Volumes
    Redis --> Volumes
    Volumes --> Backups
    LiteLLM --> Runtime
~~~

## Request flow

### Application chat / completion

1. A project sends an OpenAI-compatible request to LiteLLM on `:4000`.
2. LiteLLM authenticates the project virtual key and enforces model allowlists.
3. The request is routed to the active llama.cpp profile (`local-general`,
   `local-coder`, `local-reasoning`, or `local-vision`).
4. Only one heavy profile is loaded on the GPU at a time.

### Human chat (Open WebUI)

1. The user sends a request through Open WebUI.
2. Open WebUI calls the UI Gateway for OCR-aware attachment handling.
3. The host gateway exposes the OpenAI-compatible endpoint used by the UI path.
4. The gateway sends the request to the active llama.cpp server.

### Retrieval-augmented generation

1. A document is uploaded to Open WebUI.
2. Apache Tika extracts text and performs OCR where required.
3. The local embedding service creates vectors.
4. Vectors and metadata are stored in PostgreSQL/pgvector.
5. Relevant chunks are selected and added to the local model context.

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
| Host service exposure | `127.0.0.1` only |
| Model storage | Read-only bind mount where possible |
| Secrets | Local `.env`, `secrets/`, and `projects/*.env` |
| Internet | Required only for provisioning and optional web search |

## Persistence

Persistent information is divided into:

- Docker volumes for PostgreSQL, Redis and Open WebUI state;
- `/srv/ai-station/models` for model binaries;
- `/srv/ai-station/runtime` for active heavy-profile state;
- `/srv/ai-station/backups` for timestamped backups;
- `/opt/ai-station` for version-controlled application files.

Runtime data must not be committed to Git.

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
