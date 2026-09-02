# AI Station Documentation Map

Use this page to find the authoritative source instead of copying the same
fact across multiple documents.

## Start here

| Need | Canonical document |
|---|---|
| Product intent and sale scope | [PRODUCT.md](PRODUCT.md) |
| What to build next | [ROADMAP.md](ROADMAP.md) |
| Decision index | [DECISIONS.md](DECISIONS.md) |
| Current goal and next action | [PROJECT_STATE.md](PROJECT_STATE.md) |
| Install or upgrade | [INSTALLATION.md](INSTALLATION.md) |
| Understand the system | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Integrate an application | [PLATFORM.md](PLATFORM.md) |
| Disaster recovery targets and drills | [DISASTER_RECOVERY.md](ops/DISASTER_RECOVERY.md) |
| Chat and document retention | [DATA_GOVERNANCE.md](ops/DATA_GOVERNANCE.md) |
| Implement grounded accuracy for Local Content Studio | [LOCAL_CONTENT_STUDIO_GROUNDED_ACCURACY_SPEC.md](LOCAL_CONTENT_STUDIO_GROUNDED_ACCURACY_SPEC.md) |
| Operate or recover it | [OPERATIONS.md](OPERATIONS.md) |
| Recommended models, sizes, performance, and Git size without weights | [MODELS.md](MODELS.md) |
| See the verified release snapshot | [AI_STATION_CURRENT_STATE.md](ops/AI_STATION_CURRENT_STATE.md) |
| Configure OpenCode | [OPENCODE.md](clients/OPENCODE.md) |
| Build a document notebook | [OPENWEBUI.md](clients/OPENWEBUI.md) |
| Use the code graph | [GRAPHIFY.md](clients/GRAPHIFY.md) |
| Generate music or video | [COMFYUI.md](clients/COMFYUI.md) |
| Automate workflows | [N8N.md](clients/N8N.md) |
| Use grounded research tools | [TOOL_GATEWAY.md](clients/TOOL_GATEWAY.md) |
| Diagnose a failure | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) |
| Find the correct script | [SCRIPTS.md](SCRIPTS.md) |
| Review security boundaries | [THREAT_MODEL.md](security/THREAT_MODEL.md) |
| Review architecture decisions | [ADR index](adr/README.md) |

## Authority rules

- `PRODUCT.md` owns buyer, SKU, in/out of scope, and the sale goal.
- `ROADMAP.md` owns sequential waves. It is not a calendar.
- `DECISIONS.md` indexes product decisions to ADRs; ADRs remain the
  decision bodies.
- `PROJECT_STATE.md` owns the current goal and next action. It is not
  a verified runtime snapshot.
- `ARCHITECTURE.md` owns component boundaries and request flows.
- `PLATFORM.md` owns the LiteLLM application contract and project keys.
- `ops/DISASTER_RECOVERY.md` owns RPO/RTO and restore-drill policy.
- `ops/DATA_GOVERNANCE.md` owns chat/document retention policy.
- `MODELS.md` owns the recommended-model list (size + measured
  performance), the Git application size excluding weights, and
  add/remove procedures. Machine definitions stay in manifest,
  catalog, provider, and LiteLLM config files.
- `AI_STATION_CURRENT_STATE.md` is a snapshot, not a timeline or roadmap.
- ADRs own durable decisions and trade-offs.
- `docs/research/` contains evidence and experiments; it is non-normative
  unless an accepted ADR promotes a result. The digest
  [AI_STATION_DEVELOPMENT_PLAN.md](research/AI_STATION_DEVELOPMENT_PLAN.md)
  is input only.
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
