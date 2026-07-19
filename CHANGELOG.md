# Changelog

All notable project changes should be recorded in this file.

## Unreleased

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
