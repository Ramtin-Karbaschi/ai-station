# AI Station scripts map

Day-to-day operations use **one** public entrypoint. Everything else is
install, release, or incident recovery.

## Canonical day-to-day (single CLI)

| Entry | Purpose |
|---|---|
| **`scripts/ai`** (`/usr/local/bin/ai`) | **Only** platform control plane: start/stop/restart/status/models/provider/projects/opencode/graphify/test/logs/verify/backup/disk/… |

Windows launchers call the same script:

| Launcher | Calls |
|---|---|
| `AI Station/AI Station.cmd` → `.ps1` | `ai start` (restores last heavy profile, else `general`) |
| `AI Station/AI Station Manager.cmd` | `ai <action>` (same verbs as the Manager menu, including `opencode configure`) |

Desktop copies are trampolines into `/opt/ai-station`. Do not keep a second
full `AI Station Manager.ps1` on the Desktop.

Compat shims (kept so old Desktop shortcuts / Makefile paths still work; they only `exec` `ai`):

- `scripts/start.sh` / `stop.sh` / `status.sh`
- `scripts/ai-station-user-start.sh` / `user-stop.sh`
- `scripts/ai-station-manager-action.sh` / `admin-action.sh`
- `scripts/switch-ai-station-model.sh` → `ai models use`
- `scripts/stop-ai-station-models.sh` → `ai models stop`

OpenCode's WSL-native developer runtime is managed only through this CLI:

~~~bash
ai opencode configure --dry-run
ai opencode configure
ai opencode test
ai opencode use general|coder|reasoning|ornith   # GPU warmup; picker stays open
ai opencode test --model ornith
ai models catalog
ai models add coder-qwen3-30b-a3b-q4
ai models install coder-qwen3-30b-a3b-q4
ai models remove coder-qwen3-30b-a3b-q4   # dry-run unless --confirm
ai graphify install && ai graphify extract --code-only
ai graphify query "what starts the coder profile?"
~~~

Templates live in `config/clients/opencode/`. Graphify is an optional
code-graph CLI (`config/clients/graphify/`, [clients/GRAPHIFY.md](clients/GRAPHIFY.md)).
Do not commit the generated
Windows `opencode.jsonc` (it contains the project API key). See
[clients/OPENCODE.md](clients/OPENCODE.md).

Internal helpers used by `ai start` (not user-facing):

- `scripts/lib/ai-common.sh`, `ai-models.sh`, `ai-opencode.sh`, `ai-graphify.sh`

- `scripts/compose-ai-station.sh`
- `scripts/ensure-litellm-db.sh` / `sync-litellm-db-url.sh` / `ensure-wsl-idle-timeout.sh`
- `scripts/verify.sh` / `verify-startup-stability.sh`
- `scripts/backup.sh` / `reset-openwebui-password.sh`

Offline quality has one reproducible entrypoint:

~~~bash
ai test                    # all unit and cross-file contract tests
ai test --live             # plus llama.cpp JSON/tool-call probes
make check                 # tests + Compose + manifests + documentation
~~~

`scripts/test.sh` selects `.venvs/gateway/bin/python` locally and accepts
`AI_STATION_TEST_PYTHON` for CI.

## Install / provision / release

Keep as-needed; not used by the Windows quick-start path:

- `install.sh`, `preflight-install.sh`, `validate-installer.sh`
- `provision-models.sh`, `model_provision.py`, `verify-models.sh`, `verify-model-manifest.sh`
- `model_manager.py` (catalog, add, recoverable quarantine/restore)
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

## Removed from the active tree

One-shot destructive bootstrap helpers and unreferenced duplicates were
removed or left only under local `_archive/` (gitignored). Do not restore
them unless you have a specific recovery need.
