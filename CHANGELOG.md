# Changelog

All notable project changes should be recorded in this file.

## Unreleased

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
