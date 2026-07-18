# AI Station Architecture

## Design goals

AI Station is designed around five constraints:

1. inference and document processing remain local;
2. heavy models are stored outside the source repository;
3. container and model versions are reproducible;
4. services are exposed only on loopback by default;
5. operational state can be verified through deterministic checks.

## Logical architecture

~~~mermaid
flowchart TB
    subgraph Host["Windows 11 / WSL2 host"]
        Browser["Browser"]
        UIGateway["UI Gateway :8890"]
        Gateway["AI Station Gateway :8888"]
    end

    subgraph Docker["Docker Compose"]
        WebUI["Open WebUI :3000"]
        LLM["llama.cpp LLM :8082"]
        Embedder["llama.cpp Embeddings :8090"]
        Tika["Apache Tika + Tesseract :9998"]
        Search["SearXNG :8889"]
        Postgres["PostgreSQL + pgvector :5432"]
        Redis["Redis :6379"]
    end

    subgraph Storage["Persistent storage"]
        Models["/srv/ai-station/models"]
        Cache["/srv/ai-station/cache"]
        Backups["/srv/ai-station/backups"]
        Volumes["Docker volumes"]
    end

    Browser --> WebUI
    WebUI --> UIGateway
    UIGateway --> Gateway
    Gateway --> LLM

    WebUI --> Embedder
    WebUI --> Tika
    WebUI --> Search
    WebUI --> Postgres
    WebUI --> Redis

    LLM --> Models
    Embedder --> Models
    WebUI --> Cache
    Postgres --> Volumes
    Redis --> Volumes
    Volumes --> Backups
~~~

## Request flow

### Chat

1. The user sends a request through Open WebUI.
2. Open WebUI calls the UI Gateway.
3. The UI Gateway normalizes the model name and locally processes supported
   attachments.
4. The AI Station Gateway exposes the OpenAI-compatible endpoint.
5. The gateway sends the request to the active llama.cpp server.
6. The response returns to Open WebUI.

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
| Open WebUI to gateway | Localhost or Docker host gateway |
| Container-to-container | Docker Compose network |
| Host service exposure | `127.0.0.1` only |
| Model storage | Read-only bind mount where possible |
| Secrets | Local `.env` and ignored secret files |
| Internet | Required only for provisioning and optional web search |

## Persistence

Persistent information is divided into:

- Docker volumes for PostgreSQL, Redis and Open WebUI state;
- `/srv/ai-station/models` for model binaries;
- `/srv/ai-station/cache` for resumable model caches;
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

## Known architectural constraints

- The primary supported deployment is a single NVIDIA workstation.
- Only one heavy model should be active when VRAM is constrained.
- The project is not designed for direct public internet exposure.
- Native Windows execution without WSL2 is unsupported.
- Multi-node orchestration is outside the current scope.
- The host gateway path should be tested on a clean machine before an
  unattended organizational rollout.
