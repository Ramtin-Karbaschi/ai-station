# Changelog

All notable project changes should be recorded in this file.

## Unreleased

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
