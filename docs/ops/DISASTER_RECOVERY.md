# Disaster Recovery

Date: 2026-09-02
Status: Policy plus verified RB-04 isolated restore drill. Operator console:
[OPERATIONS.md](../OPERATIONS.md).

## Targets

| Metric | Target | Notes |
|---|---|---|
| RPO | 24 hours | Maximum acceptable data loss |
| RTO | 4 hours | Time to return LiteLLM, Open WebUI, and the last heavy profile |

These numbers are operational defaults for a single sold station.
A customer may tighten them; they may not loosen them in product
docs without updating this file.

## What backup captures today

`scripts/backup.sh` writes `/srv/ai-station/backups/<timestamp>/`:

- PostgreSQL custom dump of the configured primary database
- tarball of `/srv/ai-station/data` uploads and artifacts
- `compose.yml` and `.env.example`
- `SHA256SUMS`

When `AI_STATION_OPENWEBUI_VOLUME_BACKUP=1` and Docker has the named
`ai-station-openwebui-data` volume, the same
operation also writes `ai_station_litellm.dump`, `database_backup_manifest.json`,
`ai_station_openwebui_data.tar.gz`, and `openwebui_volume_manifest.json`.
The database manifest records the earliest capture start and final capture
finish. The archive includes Open WebUI state and
the local Whisper cache/model. SQLite files are captured through the SQLite
online-backup API before archiving; live `*.db-wal` and `*.db-shm` sidecars are
not copied. The volume pair is opt-in so pre-volume backups remain valid. When
opt-in is requested but Docker or the named volume is missing, the backup
fails before publishing a partial result. The LiteLLM database name defaults
to `litellm` and can be set with `AI_STATION_LITELLM_DB`.

Model weights live under `/srv/ai-station/models` and are not copied
by this script. Recover models from the manifest install path, not
from chat backups. The volume archive is produced by
`scripts/backup-openwebui-volume.sh` and does not include `.env`, secrets,
PostgreSQL data, or model bytes outside the Open WebUI volume. The volume may
contain sensitive application state even though `.env` is excluded; keep the
backup directory private and protect copies accordingly.

## Restore

`ai backup` writes a qualifying station backup: PostgreSQL custom dump,
uploads/artifacts tarball, `compose.yml`, `.env.example`, and
`SHA256SUMS`. Discovery considers published `YYYYMMDD-HHMMSS` folders
with those files. Backup attempts that share a timestamp leave the
first completed backup in place.

Verify the latest qualifying backup (or a named timestamp) without
applying it:

~~~bash
ai restore --dry-run
ai restore --dry-run --id 20260902-120000
~~~

The command checks checksums, whether the dump looks like PostgreSQL
custom format (and lists the TOC when `pg_restore` is available), and
whether the tarball extracts into a temp directory that is then
deleted. For a complete backup it checks the LiteLLM dump and database
manifest along with the Open WebUI manifest and archive. Older backups that
predate the second database dump remain eligible for dry-run validation.

The CLI exposes dry-run validation only. Apply a production restore through
an explicit operator procedure after rehearsing the backup in isolation.

## Drill

For RB-04, run this on-demand backup while the station remains running:

~~~bash
AI_STATION_OPENWEBUI_VOLUME_BACKUP=1 ai backup
~~~

1. Run `ai restore --dry-run --id <timestamp>`. Confirm both PostgreSQL
   dumps, manifests, the Whisper model members, and successful checksums.
2. Extract uploads and artifacts to a temporary directory. Restore both
   PostgreSQL dumps into separate databases in a disposable PostgreSQL
   container with no network access and no published ports.
3. Extract the Open WebUI archive to a newly named temporary volume. Start
   Open WebUI, LiteLLM, and the last heavy profile in the isolated PostgreSQL
   network namespace. Bind the existing model weights read-only. CPU fallback
   allows this rehearsal while production is using the GPU.
4. Wait for each service, send an authenticated synthetic chat through
   isolated LiteLLM, and load the restored Whisper model offline.
5. Record elapsed time from validation through readiness and the first chat.
   Record the oldest capture age at rehearsal start from the database
   manifest. Clean up only the disposable containers and volume.

On 2026-11-22 the WSL rehearsal restored 44 Open WebUI and 66 LiteLLM
tables. Both service health checks and the restored Qwen3.8-27B profile
passed. The authenticated LiteLLM chat completed at 86.5 seconds and Whisper
loaded offline at 88.2 seconds, including 43.4 seconds of validation.
The capture spanned 69 seconds and the oldest capture was 204.8 seconds old
at drill start. The uploads and artifacts directories extracted successfully
and were both empty. The timings describe this isolated CPU rehearsal with
existing model weights. Production GPU timing, scheduled recovery-point
coverage, and recovery of lost model weights are separate operations.

## Off-host copy

An encrypted copy may go to a second disk or NAS on the same
physical customer network. Do not send backups to a public cloud as
part of the product default. Loopback policy is unchanged.

## Break-glass

If OIDC is enabled but unavailable, use the local operator account
(ADR-030) to reach Open WebUI and the `ai` CLI. Application keys at
`:4000` do not depend on SSO.
