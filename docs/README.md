# AI Station Documentation Map

Use this page to find the authoritative source instead of copying the same
fact across multiple documents.

## Start here

| Need | Canonical document |
|---|---|
| Install or upgrade | [INSTALLATION.md](INSTALLATION.md) |
| Understand the system | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Integrate an application | [PLATFORM.md](PLATFORM.md) |
| Operate or recover it | [OPERATIONS.md](OPERATIONS.md) |
| Add or remove model bytes | [MODELS.md](MODELS.md) |
| See the verified release snapshot | [AI_STATION_CURRENT_STATE.md](ops/AI_STATION_CURRENT_STATE.md) |
| Configure OpenCode | [OPENCODE.md](clients/OPENCODE.md) |
| Use the code graph | [GRAPHIFY.md](clients/GRAPHIFY.md) |
| Diagnose a failure | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Find the correct script | [SCRIPTS.md](SCRIPTS.md) |
| Review security boundaries | [THREAT_MODEL.md](security/THREAT_MODEL.md) |
| Review architecture decisions | [ADR index](adr/README.md) |

## Authority rules

- `ARCHITECTURE.md` owns component boundaries and request flows.
- `PLATFORM.md` owns the LiteLLM application contract and project keys.
- `MODELS.md` explains management; machine definitions stay in manifest,
  catalog, provider, and LiteLLM config files.
- `AI_STATION_CURRENT_STATE.md` is a snapshot, not a timeline or roadmap.
- ADRs own durable decisions and trade-offs.
- `docs/research/` contains evidence and experiments; it is non-normative
  unless an accepted ADR promotes a result.
- `CHANGELOG.md` owns chronological user-visible changes.
- `CONTRIBUTING.md` owns the three-branch Git workflow.

If two documents disagree, fix the non-authoritative copy or replace it with
a link. Do not preserve contradictions for historical context; Git and ADRs
already preserve history.

## Documentation quality

Run:

~~~bash
./scripts/docs-audit.sh
make check
~~~

The audit validates canonical files, relative links, Mermaid safety,
whitespace, and release hygiene. Operational examples must use the public
LiteLLM endpoint `http://127.0.0.1:4000/v1` for clients.
