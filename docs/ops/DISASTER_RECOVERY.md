# Disaster Recovery

Date: 2026-09-02
Status: Policy. Backup exists today. Restore dry-run and periodic
drills are Wave 0 work ([ROADMAP.md](../ROADMAP.md)). Operator
console: [OPERATIONS.md](../OPERATIONS.md).

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

- PostgreSQL custom dump (`ai_station`)
- tarball of `/srv/ai-station/data` uploads and artifacts
- `compose.yml` and `.env.example`
- `SHA256SUMS`

Model weights live under `/srv/ai-station/models` and are not copied
by this script. Recover models from the manifest install path, not
from chat backups. Open WebUI Docker volumes and the Whisper volume
(risk R10) must be in the Wave 0 drill checklist; they are not in
the tarball above.

## Restore (current vs Wave 0)

Current: restore is a documented operator procedure (checksums,
`pg_restore` list, tar extract). There is no `ai restore --dry-run`
yet.

Wave 0 adds:

~~~bash
ai restore --dry-run
~~~

That command must verify the latest backup (or a given timestamp)
without applying it: checksums, dump listable, archive extractable
to a temp dir, then delete the temp dir.

Production restore still requires explicit operator confirmation.
Never overwrite `/srv/ai-station` without that confirmation.

## Drill

After Wave 0, run `--dry-run` on a current backup before calling a
release ready. Record pass/fail in
[PROJECT_STATE.md](../PROJECT_STATE.md). Include Open WebUI volume
and Whisper volume in the checklist even if they stay a separate
copy step.

## Off-host copy

An encrypted copy may go to a second disk or NAS on the same
physical customer network. Do not send backups to a public cloud as
part of the product default. Loopback policy is unchanged.

## Break-glass

If OIDC is down after Wave 1, use the local operator account
(ADR-030) to reach Open WebUI and the `ai` CLI. Application keys at
`:4000` do not depend on SSO.
