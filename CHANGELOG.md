# Changelog

All notable project changes should be recorded in this file.

## Unreleased

### Windows launchers

- fixed `AI Station.cmd` to open the **default browser** (preserves Open WebUI
  login) instead of an isolated Edge profile;
- unified Admin + Manager into one Control Panel with Application API
  management (create/show/revoke project keys, LiteLLM UI);
- `AI Station Admin.cmd` is now a compatibility alias to Manager;
- restored `ai-station-user-start.sh` / `ai-station-user-stop.sh` used by
  Desktop `AI Station.cmd`;
- synced Desktop launchers with `/opt/ai-station/AI Station/`;
- prevented `finalize-runtime-for-github.sh` from archiving these entrypoints.

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
