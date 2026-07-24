# Implementation Plan: Adaptive Inference Fabric (Reduced Form)

Date: 2026-07-23
Updated: 2026-07-24
Status: Phases 0–5 complete on `main`. Phase 6 conditional; Phase 7 rejected on current hardware.

Governing decisions are recorded in [docs/adr](../adr/ADR-001-adaptive-inference-fabric.md).
The plan implements the reduced fabric confirmed in the
[architecture audit](AI_STATION_ARCHITECTURE_AUDIT.md), section 5.

## Gate rules (all phases)

Every phase ends only when all of the following pass:

~~~text
docker compose config --quiet
./scripts/verify.sh
./scripts/docs-audit.sh
./scripts/release-audit.sh   (Errors: 0, Warnings: 0)
git diff --check
all tests introduced by the phase
~~~

No phase may remove a working path before its replacement passes
acceptance. No phase may weaken an audit to pass it.

## Phase 0 — Audit (this change set)

Delivered: architecture audit, hardware profile, technology matrix, risk
register, threat model, proposed ADRs 001-007, Cursor project rules,
this plan. No runtime change.

## Phase 1 — Control-plane foundation and hygiene

Runtime behavior preserved except two approved security fixes.

1. Bind host gateways to `127.0.0.1` (fixes risk R1); add a listener
   assertion to `verify.sh`.
2. Restore manifest completeness (risk R2): add reasoning and vision
   models with immutable revisions and SHA-256; move the orphaned
   Qwen3-Coder-Next set to `/srv/ai-station/quarantine` through a
   documented, reversible procedure.
3. Introduce `config/providers.yaml` (provider registry schema v1) and an
   adapter layer in the gateway that reads it; llama.cpp remains the only
   registered engine, so behavior is identical.
4. Admission controller with dry-run: VRAM/RAM/storage budget model fed by
   `config/hardware-profile.json`; decisions START,
   START_WITH_REDUCED_CONTEXT, STOP_CONFLICTING_PROVIDER_AND_START, QUEUE,
   FALLBACK, REJECT; wire `ai provider start <id> --dry-run`.
5. Benchmark harness skeleton under `benchmarks/` (schema, runners, public
   datasets) and a recorded llama.cpp baseline for the general and coder
   profiles.
6. Enable and contract-test tool calling and JSON-schema output on
   llama.cpp (risk R9).
7. Healthchecks for Redis and SearXNG (risk R13); archive dead `infra/`
   configs and unused `apps/` trees (risk R11).
8. Update drifted docs (D1-D6 in the audit) and `.env.example` names.

Exit evidence: baseline benchmark JSON committed under
`benchmarks/results/`, admission dry-run tests green, release audit clean.

## Phase 2 — Experimental provider: SGLang

Candidate justified in [ADR-002](../adr/ADR-002-primary-interactive-engine.md).

- Digest-pinned SGLang container, localhost-only, Compose profile
  `sglang-experimental`, never started by default.
- AWQ Marlin artifact of the same model family as the incumbent
  general model, manifest-pinned with SHA-256.
- Health endpoint, Prometheus metrics, uninstall path, rollback note.
- Admission controller treats it as a heavy provider (mutually exclusive
  with llama.cpp heavy profiles).

**Status (2026-07-24):** profile provisioned; AWQ snapshot verified; image
pulled. Serve attempts failed on 24 GiB (see Phase 3).

## Phase 3 — Benchmark and decision

Run the harness against llama.cpp and SGLang with identical prompts,
context ladders, sampling, and concurrency. Decision per ADR-002 rules:
promote / retain-as-optional / reject / postpone.

**Status (2026-07-24):** **reject promotion**. Evidence:
`benchmarks/results/20260724/sglang/general-qwen3.6-awq-oom.json` and
updated ADR-002. Production remains llama.cpp.

## Phase 4 — Retrieval evaluation

Public-safe corpus; measure Recall@K, MRR, nDCG, latency, index size,
ingestion time on pgvector; only if a measured gap matters for real
workloads, trial Qdrant as an optional profile per
[ADR-005](../adr/ADR-005-retrieval-engine.md).

**Status (2026-07-24):** lexical public-safe baseline committed
(`benchmarks/results/20260724/retrieval/lexical-public-safe-v1.json`).
pgvector retained; Qdrant not installed.

## Phase 5 — Document router

Golden extraction test set (non-sensitive fixtures incl. Persian scans);
then trial Docling behind a router (Tika default, Docling for complex
PDFs) per [ADR-006](../adr/ADR-006-document-router.md).

**Status (2026-07-24):** golden fixtures + Tika baseline 5/5
(`benchmarks/results/20260724/documents/tika-golden-v1.json`). Docling
not installed.
## Phase 6 — NVIDIA optimization (conditional)

TensorRT-LLM NGC container for one curated model, only after provider
abstraction and harness are stable, and only if NVFP4/FP8 paths prove out
under WSL2 on this machine.

## Phase 7 — Heterogeneous frontier lab (rejected on current hardware)

KTransformers requires AVX-512/AMX and RAM this host does not have
(audit section 1, hardware profile). Revisit only after a hardware change.
