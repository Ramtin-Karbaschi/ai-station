# Archived input: operational development plan

Date: 2026-09-02
Status: Non-normative. This file is an English digest of an external
analysis of the project documents. Canonical product intent,
sequence, and decisions live in [PRODUCT.md](../PRODUCT.md),
[ROADMAP.md](../ROADMAP.md), [DECISIONS.md](../DECISIONS.md), and
ADR-030 through ADR-034. Do not treat this digest as a schedule or as
an architecture decision.

The source analysis is not stored in this repository. Repository
hygiene requires English-only source text.

## What the source claimed

AI Station is a local (on-prem / edge) generative-AI workstation on
Windows 11 + WSL2 or Linux. The analysis described a mature internal
architecture (ADRs, loopback binds, digest-pinned images, SHA-256
models, `ai` CLI, LiteLLM `:4000`) that answers "what it is" and "how
it is wired" better than "how it is sold, operated at org scale, and
recovered."

Recorded SWOT themes:

- Strengths: local data, one-heavy-GPU discipline, ADR trail,
  reproducibility, OCR/ASR for local languages, OpenAI-compatible
  gateway, Windows Manager.
- Weaknesses: no end-user SSO, thin observability, single-GPU failure
  domain, incomplete DR (backup exists, RPO/RTO and restore drills do
  not), no usage-anomaly signal after ADR-029, no chat/document
  retention policy, no media content filter, no LoRA, no non-technical
  user guide. License tracking was listed; it is not an engineering
  workstream here (pre-launch owner gate).
- Opportunities: sellable / white-label product, compliance pack,
  domain LoRA, voice assistant, n8n workflow templates.
- Threats: single GPU, upstream license changes, operator-knowledge
  concentration, cheaper cloud tokens, unbounded keys if leaked.

Priority gaps in the source (impact x cost): observability stack;
DR RPO/RTO; data retention; RBAC/SSO via LDAP or OIDC; media
moderation; second GPU as failover; soft usage alerts; license
columns; LoRA; end-user training; cost/ROI report; catalog review
cycle.

The source proposed calendar phases (0-1 / 1-3 / 3-6 / 6-12+ months)
and a Prometheus + Grafana + Loki first step.

## Filters applied before promotion

Operator constraints on 2026-09-02, recorded in the canonical docs:

| Source recommendation | Canonical treatment |
|---|---|
| LDAP or OIDC | SSO/OIDC only (ADR-030). LDAP rejected. |
| Second GPU as failover-only, late phase | Multi-GPU capability now; default remains one GPU; concurrent one-heavy-profile per GPU; tensor-parallel opt-in (ADR-031). |
| Not mentioned | Optional NPU offload for CPU-class work (ADR-032). |
| Restore TPM/RPM or leave a hole | Keep ADR-029 unlimited defaults; add soft alerts only (ADR-033). |
| Prometheus + Grafana + Loki immediately | Rejected as the next increment; lean alerts from existing signals (ADR-034). |
| Calendar Gantt | Removed. Sequential waves with acceptance gates (ROADMAP). |
| License catalog and ISO/NIST packs as engineering | Deferred to a pre-launch owner gate. Not a development blocker. |

Promote a claim from this digest only by accepting an ADR or editing
PRODUCT / ROADMAP.
