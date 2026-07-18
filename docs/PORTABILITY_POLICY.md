# AI Station Portability Policy

AI Station is portable at the repository and Compose level, but it has one canonical Linux/WSL installation root:

`/opt/ai-station`

This is intentional.

The supported installation flow must install or clone the repository into that path, then place runtime data, model files, backups, and large generated artifacts outside the Git repository.

## Repository portability

The repository must not depend on machine-specific secrets, local backups, local model binaries, or generated runtime state.

The Compose file list is stored with relative paths:

```text
COMPOSE_FILE=compose.yml:compose.hardening.yaml
Runtime data policy

The following must not be committed:

.env
model files
database files
backup files
generated logs
runtime uploads
local support bundles
Canonical path policy

References to /opt/ai-station are allowed only in files that intentionally define installation, operations, local launchers, service definitions, diagnostics, or current-state documentation.

Any new occurrence of /opt/ai-station outside the allowlist should be reviewed before release.
