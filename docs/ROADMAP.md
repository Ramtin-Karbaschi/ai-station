# AI Station Roadmap

Date: 2026-09-02
Status: Canonical build sequence. No calendar. A wave starts as soon
as the previous wave meets its acceptance criteria.

Product intent: [PRODUCT.md](PRODUCT.md).
Decisions: [DECISIONS.md](DECISIONS.md).
Current pointer: [PROJECT_STATE.md](PROJECT_STATE.md).
Source analysis (non-normative):
[research/AI_STATION_DEVELOPMENT_PLAN.md](research/AI_STATION_DEVELOPMENT_PLAN.md).

## Wave graph

~~~mermaid
flowchart TB
  waveD["Wave D: documents"]
  wave0["Wave 0: operational risk"]
  wave1["Wave 1: SSO"]
  wave2["Wave 2: hardware"]
  wave3["Wave 3: product surfaces"]
  waveD --> wave0
  wave0 --> wave1
  wave1 --> wave2
  wave2 --> wave3
~~~

## Wave D — documents

Write the product canon and the ADRs that filter the archived
analysis. No runtime change.

Acceptance:

- [PRODUCT.md](PRODUCT.md), this file, [DECISIONS.md](DECISIONS.md),
  and [PROJECT_STATE.md](PROJECT_STATE.md) exist
- ADR-030 through ADR-034 exist and are indexed
- [ops/DISASTER_RECOVERY.md](ops/DISASTER_RECOVERY.md) and
  [ops/DATA_GOVERNANCE.md](ops/DATA_GOVERNANCE.md) exist
- `./scripts/docs-audit.sh` exits 0

## Wave 0 — operational risk, no new architecture

Implement the policies already written. Do not add containers.

1. Disaster recovery: document RPO/RTO (already in
   [ops/DISASTER_RECOVERY.md](ops/DISASTER_RECOVERY.md)); add
   `ai restore --dry-run`; run one successful drill.
2. Data retention: configurable TTL for chats and documents
   ([ops/DATA_GOVERNANCE.md](ops/DATA_GOVERNANCE.md)). Default 90 days.
3. Soft usage alerts (ADR-033): notify when a project key exceeds
   about 3x its recent daily mean. Do not set TPM/RPM.
4. Lean health alerts (ADR-034): disk above 85%, CUDA OOM, always-on
   container down. Short local retention. No Prometheus/Grafana/Loki.

Acceptance:

- `ai restore --dry-run` reports whether the latest backup is
  restorable without applying it
- Retention job is off until the operator sets a TTL; default policy
  is 90 days once enabled
- Usage and health alerts fire in a contract test or documented
  dry-run; requests are never rejected by a new rate cap
- Disk use of the alert path is bounded and documented

## Wave 1 — SSO

Open WebUI and customer-facing admin use OIDC only (ADR-030).
Remove shared local end-user accounts. Keep a break-glass operator
login for install and recovery. LiteLLM project keys stay for apps.

Acceptance:

- A user can sign in with a configured OIDC issuer
- Group claims map to Admin / Member / Viewer
- LDAP is not present in compose or docs as a supported path
- Per-user login is logged without prompt content

## Wave 2 — hardware

1. Multi-GPU admission (ADR-031): `hardware-profile.json` lists GPUs;
   default `max_heavy_providers = 1`; when GPU count is greater than
   one, concurrent placement is one heavy profile per GPU;
   tensor-parallel is an explicit profile.
2. NPU detect and optional offload (ADR-032): record NPU in the
   hardware profile; candidate backends for embed / rerank / ASR
   require a local apples-to-apples benchmark vs CPU; promote only
   on the station 20% rule with no quality regression.

Acceptance:

- One-GPU hosts keep today's exclusivity
- `ai provider start --dry-run` explains `gpu_index` on a multi-GPU
  profile without requiring a second card in CI (fixture is enough)
- NPU absence leaves CPU embedder/reranker/ASR unchanged
- Any NPU promotion has a result under `benchmarks/results/`

## Wave 3 — product surfaces

Execute in this order, each with its own focused tests:

1. Prompt filter and audit log for ComfyUI media
2. Short non-technical user FAQ (chat, RAG upload, allowed use)
3. One-page cost / ROI report from LiteLLM spend vs a cloud tariff
   table the operator supplies
4. Catalog review procedure (last-evaluated date, active / retiring /
   experimental) before a model replacement
5. Three n8n templates (ticket reply, invoice OCR, meeting summary)
6. Optional LoRA pipeline on a small internal dataset
7. Logical tenant isolation for a first external sale
8. Voice MVP: existing ASR + TTS + LLM on loopback

Acceptance is per item: documented, tested, and linked from this
file when that item ships. Do not batch-merge unrelated surfaces.

## Not an engineering wave

These items from the archived analysis are **not** sequenced here:

- Model-license inventory as a development task
- ISO / NIST / OWASP compliance packs as a build phase
- Buying a second GPU only as failover
- Calendar milestones
- Prometheus + Grafana + Loki as the first observability install

Legal clearance remains an owner pre-launch gate ([PRODUCT.md](PRODUCT.md)).
