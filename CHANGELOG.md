# Changelog

All notable project changes should be recorded in this file.

## Unreleased

- **Qwen3.8 context:** general/reasoning now use **262144** with Q4 KV and
  flash-attn. Measured 2026-08-27: 138801-token ingest in 190.4 s at
  22401 MiB VRAM (`benchmarks/results/20260827/qwen38-262144-q4-ingest-128k.json`).
- **Document intelligence:** Tika first, PaddleOCR-VL-1.6 when available,
  Tesseract fallback. Rerankers are never in the OCR path (ADR-006).
- **Speech:** `POST /v1/audio/transcriptions` on the host gateway.
  Qwen3-ASR-1.7B is primary; faster-whisper-large-v3 stays the fallback
  (ADR-027).
- **Local AI Studio:** capability map in `config/studio/capabilities.yaml`.
  All 70 studio-era manifest ids size-match (**361.62 GiB**), including
  LTX-2.5 NVFP4 and Hunyuan3D 2.1 Comfy-Org checkpoint. New packs stay
  `configured_pending_smoke` until a local ComfyUI smoke. Fish S2 Pro is
  local/personal use.
- **Open WebUI RAG:** Knowledge is `halfvec(4096)` with
  `PGVECTOR_INITIALIZE_MAX_VECTOR_LENGTH=4096` and
  `PGVECTOR_USE_HALFVEC=true`. A sentinel HNSW on `subvector(...,4000)`
  satisfies Open WebUI's index check (pgvector HNSW max is 4000-d).
  Retrieval stays exact cosine. The previous default 1536 restarted the
  UI after the 8B embedding migration.
- **Compose orphans:** `COMPOSE_FILE` includes
  `compose.comfyui.experimental.yaml` so option 1 / `ai start` no longer
  warns that `ai-station-comfyui-experimental` is an orphan. Overlay
  start/stop use the same project chain. `--remove-orphans` is still
  forbidden (it would delete chat or media containers).
- **Chat output cap:** Open WebUI `DEFAULT_MODEL_PARAMS.max_tokens` is 4096
  (was 1024). Mid-sentence cuts were `finish_reason=length` on the client
  output budget, not the 8192 context window. LiteLLM has no second cap.
- **ADR-022 Accepted:** the 0.6B embedder runs CPU-only (`gpus: []`,
  `-ngl 0`) so Open WebUI RAG stays up beside one heavy GPU chat
  profile. The GPU embedder had been exiting 0 after a CUDA error.
  ComfyUI start no longer stops the embedder.
- **Service directory:** `ai start` and `ai status` print always-on vs
  on-demand loopback URLs (Open WebUI, LiteLLM API/Admin, SearXNG, Tika,
  embedding, reranker, ComfyUI, n8n, Graphify, OpenCode). README local
  endpoints match. Windows Manager labels ComfyUI as the media studio,
  not experimental.
- **Live ops:** `scripts/live-ops-smoke.sh` sequentially probed every
  catalog chat profile through LiteLLM `:4000`, CPU embed/rerank, and
  workstation tools. Summary:
  `benchmarks/results/20260823/live-ops-summary.json`.
- **ADR-021 Accepted:** optional n8n workflow client on loopback
  `:5678`. CPU-only, off by default, digest-pinned. Workflows call
  LiteLLM `:4000/v1` only. Does not replace OpenCode, Open WebUI, or
  ComfyUI.
- **Retained models:** Ornith 1.5, Qwen3.8, LongWriter-Zero Q4, and
  ComfyUI MiniMax Music 3 / MiniMax H3 / FLUX.2 are never experimental
  and must never be deleted. Manifest marks them `operator_retained`;
  `ai models remove` refuses them. Bytes were restored after the
  incorrect 2026-08-23 disk-lighten; SHA-256 matched the manifest.
- **Recommended models:** `docs/MODELS.md` lists every manifest pack
  with GiB sizes and measured performance. The Git application size
  excluding model weights is documented there.
- **Compose unit:** one Docker Compose project. `ai start` is the
  operator entry. `COMPOSE_FILE` consistently includes
  `compose.models.yml`.
- **ADR-019 Accepted:** optional `qwen38` llama.cpp profile pins Unsloth
  Qwen3.8-27B UD-Q4_K_M GGUF plus F16 mmproj (native vision + tools +
  thinking). Does not replace `general`, `coder`, or `vision`. Official
  BF16 safetensors are not downloaded.
- **ADR-020 Amended:** optional `longwriter` llama.cpp profile pins
  mradermacher LongWriter-Zero-32B **Q4_K_M** after a live Q8_0 smoke
  on this 24 GiB GPU failed the suitability bar (~2.7 tok/s, 108 MiB
  free VRAM, CPU offload). Q4_K_M live smoke via LiteLLM `:4000` was
  5.696 s / 22.47 tok/s. Q8_0 bytes were removed. Does not replace
  `general` or `reasoning`.

## 2026-08-22

### Model download reliability

- Hugging Face provisioner uses a 600s stream timeout, retries, stale
  lock cleanup, and HTTP Range resume for incomplete destination files
  (huggingface_hub's 10s default aborted multi-GB transfers).

### Ornith 1.5 and FLUX.2-dev

- **ADR-017 Accepted:** the optional `ornith` llama.cpp profile now
  pins Ornith 1.5 35B-A3B Q4_K_M GGUF. Coder stays the production
  default.
- **ADR-018 Accepted:** FLUX.2-dev still images on the existing
  experimental ComfyUI overlay (city96 Q4 GGUF + Comfy-Org VAE/FP4
  encoder). Open WebUI image generation stays off. No LiteLLM image
  route. Live image smoke is separate from `make check`.

### Unused model purge

- Removed unmanaged OCR snapshots (DeepSeek-OCR-2, dots.ocr, dots-mocr),
  unused experimental SGLang AWQ shard pins, and superseded Ornith 1.0
  (quarantine + Hugging Face cache). They are not in the live manifest.
- Removed the unused experimental SGLang Compose overlay, provider,
  uninstall script, and bench config. ADR-002 still rejects promotion;
  the 2026-07-24 OOM JSON remains as evidence. Persian OCR stays on
  Tika + Tesseract (`fas`).

### Operator console, selectable outputs, Graphify map

- **ADR-016 Accepted:** `ai` and Windows Manager remain the privileged
  console. Operators pick media, Graphify, and export directories with
  `ai output`. `ai graphify view` serves the upstream Graphify HTML plus
  a loopback station map on `127.0.0.1:4174`. No second admin API.

### Open WebUI hybrid RAG notebooks

- Wired the existing CPU Qwen3 reranker into Open WebUI hybrid search
  (BM25 + pgvector, top 20 candidates, 3 chunks in the prompt). Notebooks
  are Workspace → Knowledge; `ai projects` remains LiteLLM API keys. See
  `docs/clients/OPENWEBUI.md`.

### Experimental ComfyUI MiniMax media studio

- **ADR-015 Accepted:** isolated ComfyUI overlay for MiniMax Music 3 and
  MiniMax H3 next to Open WebUI. Loopback `:8188`, off by default, one
  heavy GPU at a time. Chat remains LiteLLM `:4000`. See
  `docs/clients/COMFYUI.md`. Live Music3 and H3 text-to-video smokes passed
  on 2026-08-22; ComfyUI stays experimental. Generated media, prompt
  dumps, and `/system_stats` snapshots stay gitignored; only slim
  `health.json` and `*-smoke.json` files are kept under
  `benchmarks/results/`.

### Operator simplification

- retried `docker compose up` on Docker Desktop WSL port-proxy HTTP 500
  (`/forwards/expose`) so Start is not a one-shot failure on Tika `:9998`;
- Windows Desktop launchers now trampoline into `/opt/ai-station` instead of
  keeping a second, stale copy of the Manager panel;
- restored the missing `Read-SafeId` helper in the Windows Manager;
- removed the unused Admin.cmd alias from `AI Station/`;
- documented a three-branch Git workflow (`development`, `stage`, `main`) and
  stopped treating extra branch names as part of the supported process;
- tracked the Postgres schema under `infra/postgres/` and described the host
  as Linux or Windows+WSL in the architecture diagram;
- restored execute bits on `scripts/test.sh` and other operator entrypoints;
- resolved `AI_STATION_TEST_PYTHON=python` from PATH so the test runner
  can use an unqualified interpreter name;
- pointed gateway tests at the checkout tree (`AI_STATION_PROJECT_DIR`) so
  clones do not depend on `/opt/ai-station` existing on the machine;
- pinned PyYAML in the gateway requirements so catalog and contract tests
  do not rely on a transitive uvicorn extra;
- kept image-lock quality gates on digest pins; local image bytes are
  required only after `docker compose pull` via `--require-local`;
- stopped publishing GitHub metadata directories; `make check` is the
  offline quality gate;
- replaced the superseded OpenCode compaction ADR with `docs/adr/README.md`
  as the live decision index;
- folded install, portability, and second-machine clone steps into
  `docs/INSTALLATION.md`; Linux and Windows+WSL now share one guide;
- added `ai models add` for curated install and for registering a new
  Hugging Face GGUF with an immutable revision, size, and SHA-256;
- extracted model CLI logic into `scripts/lib/ai-models.sh`;
- regrouped the Windows Manager around Lifecycle, Models, Clients, and
  Operations with sequential menu numbers and a first-class Add action;
- removed completed research snapshots and the overlapping path-quarantine
  script in favor of manifest-driven quarantine.

### Production-readiness and operator safety

- added the canonical `scripts/test.sh` runner, `ai test`, `make test`, and
  `make check`; quality gates validate Python contracts, Compose configuration,
  manifests, documentation, and Windows PowerShell syntax;
- added recoverable model catalog/install/verify/quarantine/restore workflows;
  destructive model removal remains unavailable and active/required models are
  protected by explicit policy gates;
- replaced the command-string Windows manager with a typed PowerShell control
  panel that passes validated arguments directly to WSL;
- removed the abandoned alternate-runtime research path so Docker Compose is
  the sole documented and tested production runtime;
- refactored the canonical documentation map and current-state snapshot, and
  added three project skills for operations, engineering, and client
  integration;
- corrected the OpenCode capability contract: DeepSeek reasoning supports chat
  but is not advertised as tool-calling; coder, general, and Ornith retain
  their verified tool capability.

### Graphify code knowledge graph

- **ADR-012 Accepted:** pinned `graphifyy==0.9.47` in an isolated venv
  as an optional coding-assistant graph (not a pgvector replacement).
  Day-to-day CLI: `ai graphify install|configure|extract|query|path|explain|uninstall`.
  Default extract is `--code-only` (tree-sitter, no GPU). `--docs` uses
  LiteLLM `http://127.0.0.1:4000/v1` only; install now includes the pinned
  `openai` and `pdf` extras (LiteLLM client + local PDF parsing, not a
  public cloud SDK). Graphs live under
  `/srv/ai-station/runtime/graphify/` (gitignored). OpenCode gets a short
  `/graphify` command plus a one-shot plugin reminder; the upstream
  700-line skill is not installed so repository guidance stays concise. See
  `docs/clients/GRAPHIFY.md`.

### OpenCode WSL developer environment

- amended ADR-009 so the verified client runs inside WSL as the dedicated
  non-root user `aidev`; native Windows Desktop on a WSL UNC worktree is no
  longer presented as the canonical development path;
- added a reproducible OpenCode 1.18.19 runtime manifest and checksum-verifying
  installer under `/usr/local/lib/ai-station/opencode/`;
- added `ai opencode doctor`, `run`, and a live acceptance harness that
  requires real tool use, a file edit, and a passing unit test;
- added `ai opencode parity --live`, a multi-file development acceptance
  contract, and an explicit matrix separating verified agentic parity from
  proprietary editor-only product services;
- pinned Pyright, Bash Language Server, Ruff, shfmt, ShellCheck, and the stable
  OpenCode VS Code extension; installation now blocks high-severity npm
  advisories;
- enabled LSP, formatter, snapshots, project skills, 40 build iterations, and a
  4096-token coder output budget while denying external-worktree access;
- replaced custom compaction state machines with supported native
  `auto`/`prune`/`reserved` configuration and marked ADR-010 superseded;
- extracted the OpenCode subsystem from the main `scripts/ai` dispatcher into
  `scripts/lib/ai-opencode.sh`;
- updated Windows Manager option 29 to launch the WSL-native non-root developer
  client and option 38 to repair/install/configure it;
- retained the verified model contract: coder, general, and Ornith support
  tools; DeepSeek reasoning is chat-only; all use LiteLLM `:4000/v1`.

### Install pack on GitHub

- added `install/windows/Install-AIStation.ps1` and
  `install/linux/install-ai-station.sh` with ready one-liners;
- added `scripts/build-install-pack.sh` to publish
  `ai-station-install-pack.zip` on GitHub Releases;
- linked Download & install from the main README.

### Security and dependencies

- upgraded gateway Python deps (`fastapi`/`starlette`/`uvicorn`) to clear
  known Starlette advisories reported by `pip-audit`.

### Documentation and repository hygiene

- removed unused legacy app trees (`apps/api`, `apps/web`, `apps/worker`,
  `apps/ocr`) and the destructive one-shot `finalize-runtime-for-github.sh`;
- tracked `.env.models.example`; removed orphan local `.env.console*` /
  `.env.openwebui` templates with no Compose consumers;
- fixed script executable bits in Git so clones can run `./scripts/*.sh`;
- refreshed README, Persian guide, models, current-state, and research docs
  after Phases 2–5 decisions.

### Phase 2–5 — Adaptive Inference Fabric decisions

- provisioned digest-pinned experimental SGLang overlay and AWQ snapshot
  tooling; recorded serve failure on 24 GiB (hybrid MoE memory);
- **ADR-002 Accepted:** retain llama.cpp; reject SGLang promotion on this
  workstation for the incumbent model family;
- Phase 4 lexical retrieval baseline committed; pgvector retained (ADR-005);
- Phase 5 document golden set + Tika baseline 5/5; Docling deferred (ADR-006);
- cleaned rejected experimental weights and unused images from the workstation.

### Phase 1 — Adaptive Inference Fabric control plane

- bound host and UI gateways to `127.0.0.1` with checked-in systemd units;
- added `config/providers.yaml`, admission dry-run, and `ai provider` CLI;
- completed model manifest entries for reasoning, vision, and mmproj;
- quarantined the unreferenced Qwen3-Coder-Next shard set via
  `scripts/quarantine-model-path.sh`;
- added inference benchmark harness and llama.cpp baseline results;
- enabled tool-calling / JSON catalog flags with contract tests;
- added Redis and SearXNG healthchecks; removed unused Caddy/Prometheus stubs;
- added off-by-default SGLang experimental Compose profile (research only).

### Script hygiene

- archived unreferenced duplicate scripts and local `ui_gateway.py.bak-*`
  files to `_archive/scripts-cleanup-*`;
- documented the canonical scripts map in `docs/SCRIPTS.md`;
- fixed `scripts/ai` so `/usr/local/bin/ai` resolves its install root through
  the symlink correctly.

### Windows launchers

- fixed `AI Station.cmd` to open the **default browser** (preserves Open WebUI
  login) instead of an isolated Edge profile;
- unified Admin + Manager into one Control Panel with Application API
  management (create/show/revoke project keys, LiteLLM UI);
- `AI Station Admin.cmd` is now a compatibility alias to Manager;
- restored `ai-station-user-start.sh` / `ai-station-user-stop.sh` used by
  Desktop `AI Station.cmd`;
- synced Desktop launchers with the repository `AI Station/` directory.

### Local GenAI platform

- added LiteLLM gateway on `127.0.0.1:4000` as the multi-project OpenAI API;
- added Compose profiles for `general`, `coder`, `reasoning`, `vision`, and
  CPU `reranker` runtimes (one heavy GPU profile at a time);
- added model and project registries under `config/registry/`;
- added the `ai` platform CLI for start/stop, model switching, and project
  API-key lifecycle;
- added external Docker network `ai-platform` for other Compose projects;
- documented the platform contract in `docs/PLATFORM.md`.

### Windows launcher

- restored the missing `ai-station-manager-action.sh` bridge used by
  `AI Station Manager.cmd`;
- updated the Windows menu for the verified Tika-based runtime;
- hardened start/stop helpers for reliable WSL invocation.

### Runtime alignment

- synchronized `config/model-catalog.json` with the verified baseline;
- simplified the host gateway to the active Compose services;
- aligned the UI gateway model map and Tika-only document path;
- repaired operational scripts that still referenced removed services;
- fixed Compose invocation to honor the locked `COMPOSE_FILE` chain.

### Documentation

- redesigned the main README;
- added English and Persian onboarding;
- added architecture, operations and troubleshooting documentation;
- added security and contribution policies;
- added MIT License and third-party notices;
- added automated documentation quality checks.

## Initial baseline — 2026-07-18

- established the verified WSL2 runtime;
- pinned registry and Dockerfile images;
- added immutable model revisions and SHA-256 validation;
- added a clean installer foundation;
- added release auditing with zero-warning acceptance.
