# AI Station Architecture Audit (Phase 0)

Status: complete
Date: 2026-07-23
Scope: read-only inspection of the repository, running services, models,
storage, and host environment. No runtime changes were made.

Throughout this document `<repo>` refers to the application repository root
(the canonical install location described in
[PORTABILITY_POLICY.md](../PORTABILITY_POLICY.md)) and `/srv/ai-station`
refers to the persistent data root.

Related Phase 0 deliverables:

- [Technology evaluation matrix](TECHNOLOGY_EVALUATION_MATRIX.md)
- [Risk register](RISK_REGISTER.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Threat model](../security/THREAT_MODEL.md)
- [Hardware profile](../../config/hardware-profile.json)
- [Proposed ADRs](../adr/ADR-001-adaptive-inference-fabric.md)

## 1. Executive assessment

### Verdict

The architecture should be **incrementally evolved**, not replaced. The
foundation (digest-pinned containers, immutable model manifest, loopback
policy, deterministic release audit, single-heavy-model GPU policy) is
sound and unusual in quality for a local workstation project. The gaps are
in the control plane (implicit scheduling, no admission control, no
benchmark evidence), reproducibility drift (three model sets on disk are
outside the manifest), and two host services that contradict the documented
localhost-only exposure.

### Strengths (verified)

1. Reproducibility controls are real, not aspirational: registry images are
   digest-pinned in `compose.images.lock.yaml`, the Tika image is built from
   a repository-controlled Dockerfile, models use immutable Hugging Face
   revisions with SHA-256, and `scripts/release-audit.sh` enforces all of it.
2. The single-heavy-model GPU policy is enforced in practice: the host
   gateway (`apps/gateway/app/main.py`) stops competing heavy Compose
   profiles before starting the requested one, with a serial queue and an
   idle-unload policy in `config/model-catalog.json`.
3. All Docker-published ports bind to `127.0.0.1`.
4. Separation of code (`<repo>`) from data (`/srv/ai-station`) is consistent.
5. GitHub Actions are pinned to immutable commit SHAs.
6. Secrets are file-based, mode-restricted, git-ignored, and the release
   audit greps for key/token patterns.
7. The documentation set is broad and mostly accurate, with a docs audit
   that validates links, whitespace, and Mermaid safety.

### Weaknesses (verified)

1. **Host gateways bind to all interfaces.** `ai-station-gateway.service`
   (uvicorn, port 8888) and `ai-station-ui-gateway.service` (port 8890,
   default `0.0.0.0` in `apps/ui-gateway/ui_gateway.py`) listen on
   `0.0.0.0`, contradicting the "loopback-only" claim in the README and
   `docs/ARCHITECTURE.md`. Confirmed with `ss -lntp`.
2. **Model manifest drift.** `/srv/ai-station/models` holds ~139 GiB across
   7 model sets, but `config/model-manifest.json` covers only 4. The
   reasoning model (DeepSeek-R1-Distill-32B, 19 GiB) and the vision model
   (Qwen3-VL-32B, 19.7 GiB) are referenced by Compose profiles and the
   runtime catalog yet cannot be re-provisioned or checksum-verified from
   the manifest. A 46 GiB Qwen3-Coder-Next shard set is referenced by
   nothing at all.
3. **No benchmark evidence.** No throughput, latency, or quality data
   exists for any engine or model. Context is capped at 8K everywhere
   without recorded justification.
4. **Dead configuration and code.** `infra/prometheus/prometheus.yml` and
   `infra/caddy/Caddyfile` reference services (`api:8080`, `web:80`) that
   do not exist in any Compose file; `apps/api`, `apps/worker`, `apps/ocr`,
   and `apps/web` are not referenced by Compose, the Makefile, or scripts.
5. **GPU runs at capacity with zero headroom.** At scan time 23,956 of
   24,463 MiB VRAM were in use (general model + GPU-resident embedder at 8K
   context). Any additional GPU workload will fail or degrade unpredictably.
6. **Scheduling logic is trapped inside the gateway.** Model lifecycle,
   readiness polling, and profile exclusivity are hardcoded against
   llama.cpp Compose services; adding any second engine requires editing
   gateway internals.
7. **No tool calling.** Every catalog entry has `supports_tools: false`;
   the platform cannot serve agent workloads even though the models
   (Qwen3 family) support tool calling upstream.
8. `.env.example` drift: it lists `GENERAL_CONTEXT`/`GENERAL_MODEL_FILE`
   while the Compose model overlay consumes `LLM_GENERAL_CONTEXT`/
   `LLM_GENERAL_MODEL_FILE` from `.env.models`.

### Highest-value improvements (ordered)

1. Bind both host gateways to `127.0.0.1` (config-only, immediate).
2. Bring all deployed models into the manifest (or quarantine the orphaned
   Qwen3-Coder-Next set) so provisioning is reproducible again.
3. Build the benchmark harness and capture a llama.cpp baseline before any
   engine discussion continues.
4. Extract the provider registry and admission logic from the gateway into
   a declarative control plane (Phase 1), keeping runtime behavior
   unchanged.
5. Enable and verify tool calling on the general/coder models.
6. Delete or archive dead `infra/` configs and unused `apps/` trees.

## 2. Current architecture map

### 2.1 Request and inference flow

~~~mermaid
flowchart TB
    subgraph HostWSL["WSL2 host processes (systemd)"]
        UIGW["UI Gateway :8890<br/>binds 0.0.0.0 (finding W1)"]
        GW["Host Gateway :8888<br/>binds 0.0.0.0 (finding W1)<br/>model switch + serial queue"]
    end

    subgraph Compose["Docker Compose (ports bind 127.0.0.1)"]
        OWUI["Open WebUI :3000"]
        LITE["LiteLLM Gateway :4000<br/>per-project virtual keys"]
        HEAVY["llama.cpp heavy profile<br/>one of: general :8082 | coder :8083<br/>reasoning :8084 | vision :8085"]
        EMB["llama.cpp embedder :8090"]
    end

    Browser["Browser"] --> OWUI
    OWUI -->|"OpenAI API"| UIGW
    UIGW -->|"OCR-aware attachment rewrite"| GW
    GW -->|"docker compose start/stop profiles"| HEAVY
    Apps["Application projects"] -->|"virtual key"| LITE
    LITE --> HEAVY
    LITE --> EMB
~~~

### 2.2 RAG and document-processing flow

~~~mermaid
flowchart LR
    U["Upload in Open WebUI"] --> TIKA["Apache Tika 3.3.0 + Tesseract<br/>fas+eng OCR :9998"]
    TIKA --> CH["Token chunking 512/64"]
    CH --> EMBED["Embedder Qwen3-0.6B Q8 :8090"]
    EMBED --> PGV[("PostgreSQL 17 + pgvector")]
    Q["Chat query"] --> EMBED2["Query embedding"]
    EMBED2 --> PGV
    PGV -->|"top-k 3"| CTX["Context assembly"]
    SEARX["SearXNG :8889"] -->|"web results"| CTX
    CTX --> LLM["Active llama.cpp model"]
~~~

The reranker (Qwen3-Reranker-0.6B, CPU profile) exists but is not part of
the default retrieval path.

### 2.3 Persistence and model storage

~~~mermaid
flowchart TB
    subgraph Volumes["Docker volumes"]
        PG["ai-station_pgdata"]
        RD["ai-station_redisdata"]
        OW["ai-station-openwebui-data<br/>includes Whisper large-v3 cache"]
    end

    subgraph SRV["/srv/ai-station"]
        M["models (~139 GiB, read-only bind mounts)"]
        B["backups (~3.1 GiB)"]
        R["runtime (active-heavy-profile marker)"]
        A["audits"]
        QU["quarantine"]
    end

    Postgres["postgres"] --> PG
    Redis["redis"] --> RD
    OpenWebUI["open-webui"] --> OW
    Llama["llama.cpp services"] -->|":ro"| M
    Gateway["host gateway"] --> R
~~~

### 2.4 Network boundaries and trust zones

~~~mermaid
flowchart TB
    subgraph Internet["Internet (egress only)"]
        SE["Upstream search engines"]
        HF["Hugging Face (provisioning only)"]
        GHCR["Registries (provisioning only)"]
    end

    subgraph Windows["Windows 11 host"]
        subgraph WSL["WSL2 VM"]
            subgraph Loopback["127.0.0.1 published ports"]
                P3000["3000 WebUI"]
                P4000["4000 LiteLLM"]
                P5432["5432 Postgres"]
                P6379["6379 Redis"]
                P8xxx["8082-8091 model servers"]
                P8889["8889 SearXNG"]
                P9998["9998 Tika"]
            end
            subgraph AllIf["0.0.0.0 listeners (finding W1)"]
                P8888["8888 Host Gateway"]
                P8890["8890 UI Gateway"]
            end
            NET1["ai-station_default network"]
            NET2["ai-platform external network"]
        end
    end

    SearXNG2["searxng"] --> SE
    Provision["provisioning scripts"] --> HF
    Provision --> GHCR
~~~

### 2.5 Failure and fallback paths (current behavior)

~~~mermaid
flowchart TB
    REQ["Chat request for model X"] --> GWD{"Gateway: is X active?"}
    GWD -->|"yes"| FWD["Forward to llama.cpp"]
    GWD -->|"no"| STOP["Stop other heavy profiles"]
    STOP --> START["compose --profile X up"]
    START --> WAIT{"Ready within ~16 min poll?"}
    WAIT -->|"yes"| FWD
    WAIT -->|"no"| E503["HTTP 503 with stage detail"]
    FWD --> OK["Response"]
    FWD -->|"llama.cpp crash"| RESTART["Docker restart: unless-stopped"]
    E503 --> MANUAL["Manual recovery (scripts/ai doctor path absent)"]
~~~

There is no automatic fallback provider, no admission check before start
(the start can OOM the GPU if VRAM assumptions are wrong), and no recorded
model-load-time metric.

## 3. Component inventory

| Component | Purpose | Deployment | Version (verified) | Port | Data path | Health check | Backup need | Retention decision |
|---|---|---|---|---|---|---|---|---|
| Open WebUI | Chat UI, RAG orchestration | Compose, digest-pinned | image digest `a26effeb...` | 3000 | volume `ai-station-openwebui-data` | HTTP, healthy | yes (volume) | production default |
| LiteLLM gateway | Multi-project OpenAI API, virtual keys | Compose, digest-pinned | `litellm-database` digest `72360d8b...` | 4000 | Postgres (`litellm` DB) | liveliness probe | via Postgres | production default |
| Host Gateway | Model switching, serial queue, OpenAI proxy | systemd + venv | app v0.4.0 | 8888 | `/srv/ai-station/runtime` | `/health` | no (stateless) | production default; logic to be extracted in Phase 1 |
| UI Gateway | OCR-aware attachment rewriting for WebUI | systemd, stdlib Python | unversioned | 8890 | none | `/health` | no | production default; fold into gateway later |
| llama.cpp (heavy) | GPU inference, one profile at a time | Compose profiles, digest-pinned | build b9859 (commit `4fc4ec554`, 2026-07-02) | 8082-8085 | models `:ro` | `/v1/models` | models re-provisionable | production default |
| llama.cpp embedder | Embeddings (Qwen3-0.6B Q8, GPU) | Compose, same image | b9859 | 8090 | models `:ro` | `/v1/models` | no | production default; evaluate CPU placement |
| llama.cpp reranker | Reranking (CPU profile, off by default) | Compose profile | b9859 | 8091 | models `:ro` | `/v1/models` | no | optional profile |
| PostgreSQL + pgvector | App DB, vectors, LiteLLM state | Compose, digest-pinned | pgvector/pgvector pg17 | 5432 | volume `ai-station_pgdata` | `pg_isready` | yes (dumps) | production default |
| Redis | WebSocket manager, cache | Compose, digest-pinned | redis 7-alpine | 6379 | volume `ai-station_redisdata` | none (finding) | optional | production default; add healthcheck |
| SearXNG | Local metasearch | Compose, digest-pinned | digest `969e3d79...` | 8889 | config `:ro` | none (finding) | no | production default; add healthcheck |
| Apache Tika + Tesseract | Extraction + fas/eng OCR | local build, base pinned | tika-fa 3.3.0.0-full | 9998 | none | TCP probe | no | production default |
| faster-whisper large-v3 | Local STT | inside Open WebUI volume | large-v3, int8 | n/a | WebUI volume cache | verify.sh loads model | yes (re-downloadable) | production default |
| Models on disk | 7 sets, ~139 GiB | `/srv/ai-station/models` | manifest covers 4 of 7 | n/a | see above | SHA-256 (manifest subset) | re-provisionable only if in manifest | fix in Phase 1 |
| Prometheus config | none active | `infra/prometheus` (unused) | n/a | n/a | n/a | n/a | no | remove or adopt in Phase 1 |
| Caddy config | none active | `infra/caddy` (unused) | n/a | n/a | n/a | n/a | no | remove |
| `apps/api`, `apps/worker`, `apps/ocr`, `apps/web` | removed 2026-07-24 | not deployed | n/a | n/a | n/a | n/a | no | removed |

Licenses: Open WebUI (BSD-3 with branding clause in recent versions),
LiteLLM (MIT), llama.cpp (MIT), PostgreSQL (PostgreSQL License), pgvector
(PostgreSQL License), Redis 7 (BSD-3), SearXNG (AGPL-3.0), Apache Tika
(Apache-2.0), faster-whisper (MIT), Tesseract (Apache-2.0). SearXNG's AGPL
applies to the unmodified container and is not linked into project code.

## 4. Documentation drift (verified contradictions)

| # | Claim | Reality | Severity |
|---|---|---|---|
| D1 | "Host service exposure: 127.0.0.1 only" (ARCHITECTURE.md) | Ports 8888 and 8890 listen on `0.0.0.0` | high |
| D2 | Manifest is "the authoritative downloaded model list" | 3 of 7 deployed model sets absent from manifest | high |
| D3 | `docs/ops/AI_STATION_CURRENT_STATE.md` lists reasoning/vision as absent from the verified baseline | Both are enabled in `config/model-catalog.json` and selectable via the gateway | medium |
| D4 | `.env.example` variable names | Compose consumes different names from `.env.models` | low |
| D5 | `infra/prometheus`, `infra/caddy` imply observability/proxy | Neither service exists in Compose | low |
| D6 | 64 GB system RAM stated as available | WSL2 exposes 47 GiB to the runtime | low (document it) |

## 5. Assessment of the Adaptive Inference Fabric hypothesis

The six-plane concept is **confirmed in reduced form**. The Experience,
Retrieval, and Document Intelligence planes already exist. The Control
Plane exists embedded in gateway code and must be extracted, not invented.
The Inference Plane should remain single-engine (llama.cpp) until the
benchmark harness produces evidence; SGLang is the first experimental
candidate (see [ADR-002](../adr/ADR-002-primary-interactive-engine.md)).
A full scheduler/policy-engine split is over-engineering for one GPU; the
admission controller and provider registry are the justified subset (see
[ADR-004](../adr/ADR-004-resource-admission-control.md)).

Target architecture (Phase 1-3 horizon):

~~~mermaid
flowchart TB
    subgraph Experience["Experience plane"]
        XW["Open WebUI"]
        XC["Cursor / IDE clients"]
        XA["Project APIs via LiteLLM"]
    end

    subgraph Control["Control plane (extracted, declarative)"]
        REG["provider registry<br/>config/providers.yaml"]
        HWP["hardware profiler<br/>config/hardware-profile.json"]
        ADM["admission controller<br/>dry-run capable"]
        LCM["lifecycle manager<br/>ai provider ..."]
        BEN["benchmark registry<br/>benchmarks/results"]
    end

    subgraph Inference["Inference plane"]
        LC["llama.cpp (production default)"]
        SG["SGLang (experimental profile, Phase 2)"]
        TRT["TensorRT-LLM (postponed, Phase 6)"]
    end

    subgraph Retrieval["Retrieval plane"]
        PGV2[("PostgreSQL + pgvector<br/>source of truth")]
        EMB2["embedder"]
        RER["reranker (optional)"]
    end

    subgraph DocIntel["Document intelligence plane"]
        TK["Tika + Tesseract (default)"]
        DL["Docling (trial, Phase 5, behind router)"]
    end

    Experience --> Control
    Control --> Inference
    Experience --> Retrieval
    Experience --> DocIntel
    Control -.->|"health, metrics"| Observ["Observability: engine-native<br/>metrics only, no external telemetry"]
~~~
