# AI Station Documentation Map

Use this page to find the public technical and operational documentation.

## Start here

| Need | Canonical document |
|---|---|
| Understand component boundaries and request flows | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Integrate an application with LiteLLM | [PLATFORM.md](PLATFORM.md) |
| Install or upgrade | [INSTALLATION.md](INSTALLATION.md) |
| Operate or recover the platform | [OPERATIONS.md](OPERATIONS.md) |
| Review disaster recovery targets and drills | [DISASTER_RECOVERY.md](ops/DISASTER_RECOVERY.md) |
| Review chat and document retention | [DATA_GOVERNANCE.md](ops/DATA_GOVERNANCE.md) |
| Review architecture decisions | [ADR index](adr/README.md) |
| Configure OpenCode | [OPENCODE.md](clients/OPENCODE.md) |
| Build a document notebook | [OPENWEBUI.md](clients/OPENWEBUI.md) |
| Generate media | [COMFYUI.md](clients/COMFYUI.md) |
| Automate workflows | [N8N.md](clients/N8N.md) |
| Diagnose a failure | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Find the correct script | [SCRIPTS.md](SCRIPTS.md) |
| See the verified release snapshot | [AI_STATION_CURRENT_STATE.md](ops/AI_STATION_CURRENT_STATE.md) |
| Review security boundaries | [THREAT_MODEL.md](security/THREAT_MODEL.md) |

## Documentation ownership

- `ARCHITECTURE.md` describes component boundaries and request flows.
- `PLATFORM.md` defines the LiteLLM application contract and project keys.
- `ops/DISASTER_RECOVERY.md` defines recovery targets and restore-drill policy.
- `ops/DATA_GOVERNANCE.md` defines chat and document retention policy.
- `MODELS.md` documents supported model packs, measured performance, and
  model add/remove procedures. Machine definitions stay in manifests,
  catalogs, provider files, and LiteLLM configuration.
- `ops/AI_STATION_CURRENT_STATE.md` records a verified runtime snapshot.
- ADRs record durable technical decisions and trade-offs.
- `docs/research/` contains evidence and experiments; it is non-normative
  unless an accepted ADR promotes a result.
- `CHANGELOG.md` records user-visible changes.
- `CONTRIBUTING.md` documents the branch workflow.

If two documents disagree, fix the non-authoritative copy or replace it with
a link. Do not preserve contradictions for historical context; Git and ADRs
already preserve history.

## Documentation quality

Run:

~~~bash
./scripts/docs-audit.sh
make check
~~~

The audit validates required files, relative links, Mermaid safety,
whitespace, and release hygiene. Operational examples must use the public
LiteLLM endpoint `http://127.0.0.1:4000/v1` for clients.
