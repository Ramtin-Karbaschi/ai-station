# AI Station scripts map

Day-to-day operations use a small surface. Everything else is install,
release, or incident recovery.

## Canonical day-to-day

| Entry | Purpose |
|---|---|
| `scripts/ai` (`/usr/local/bin/ai`) | Platform CLI: start/stop/status/models/provider/projects/logs/verify |
| `scripts/start.sh` / `stop.sh` / `status.sh` | Makefile wrappers → `ai` |
| `scripts/ai-station-user-start.sh` / `user-stop.sh` | Windows `AI Station.cmd` |
| `scripts/ai-station-manager-action.sh` | Windows Manager control panel |
| `scripts/ai-station-admin-action.sh` | Thin shim → manager-action |
| `scripts/compose-ai-station.sh` | Compose helper used by the CLI |
| `scripts/ensure-litellm-db.sh` / `sync-litellm-db-url.sh` | Required by `ai start` |
| `scripts/verify.sh` | Runtime health checks |
| `scripts/backup.sh` / `reset-openwebui-password.sh` | Manager ops |

Optional thin aliases (kept for muscle memory):

- `switch-ai-station-model.sh` → `ai models use`
- `stop-ai-station-models.sh` → `ai models stop`

## Install / provision / release

Keep as-needed; not used by the Windows quick-start path:

- `install.sh`, `preflight-install.sh`, `validate-installer.sh`
- `provision-models.sh`, `model_provision.py`, `verify-models.sh`, `verify-model-manifest.sh`
- `provision-whisper-*.sh`
- `update-image-lock.sh`, `verify-image-lock.sh`, `verify-build-lock.sh`
- `release-audit.sh`, `docs-audit.sh`, `verify-mermaid.sh`, `publish-github.sh`
- `install-systemd.sh` (loopback-bound host/UI gateway units)

## Experimental (off by default)

- `provision-experimental-snapshot.py`
- `uninstall-sglang-experimental.sh`
- Compose overlay: `compose.sglang.experimental.yaml` (research only; not promoted)

## Incident / maintenance

- `fix-openwebui-restart-loop.sh`, `fix-postgres-openwebui-password.sh`
- `ai-station-safe-cleanup.sh`, `collect-ai-station-state.sh`
- `build-tika-fa.sh`
- `quarantine-model-path.sh`

## Removed from the active tree

One-shot destructive bootstrap helpers and unreferenced duplicates were
removed or left only under local `_archive/` (gitignored). Do not restore
them unless you have a specific recovery need.
