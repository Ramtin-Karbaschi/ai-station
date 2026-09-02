# Decisions

Date: 2026-09-02
Status: Thin index. The ADR is the source of truth. Do not duplicate
ADR bodies here.

Product: [PRODUCT.md](PRODUCT.md).
Sequence: [ROADMAP.md](ROADMAP.md).
Full log: [adr/README.md](adr/README.md).

## Productization (2026-09-02)

| Decision | ADR |
|---|---|
| Human identity is SSO / OIDC only; LDAP is rejected; break-glass operator remains | [ADR-030](adr/ADR-030-sso-only-identity.md) |
| Multi-GPU capable; default one GPU; concurrent one heavy profile per GPU; tensor-parallel opt-in | [ADR-031](adr/ADR-031-multi-gpu-default-one.md) |
| Optional NPU offload for embedding, rerank, ASR after local benchmark | [ADR-032](adr/ADR-032-optional-npu-offload.md) |
| Soft usage alerts; no default TPM/RPM (ADR-029 stands) | [ADR-033](adr/ADR-033-soft-usage-alerts.md) |
| Next observability increment is lean local alerts, not Grafana/Loki | [ADR-034](adr/ADR-034-lean-observability-increment.md) |

## Still in force (selected)

| Decision | ADR |
|---|---|
| llama.cpp is the inference core; LiteLLM is the only app API | [ADR-002](adr/ADR-002-primary-interactive-engine.md), [ADR-003](adr/ADR-003-llama-cpp-role.md) |
| Admission before GPU start; one heavy provider on a one-GPU host | [ADR-004](adr/ADR-004-resource-admission-control.md), extended by ADR-031 |
| Engine-native metrics; no SaaS telemetry | [ADR-007](adr/ADR-007-observability-boundary.md), next increment ADR-034 |
| Embedder/reranker CPU so RAG coexists with one heavy GPU profile | [ADR-022](adr/ADR-022-cpu-embedder-coexistence.md), NPU path ADR-032 |
| Virtual keys unlimited unless the operator sets `--tpm` / `--rpm` | [ADR-029](adr/ADR-029-no-default-litellm-tpm-rpm.md) |
