---
name: ai-station-engineering
description: Engineer, refactor, review, test, or document changes inside the AI Station repository. Use whenever a request changes gateway routing, llama.cpp profiles, LiteLLM, OpenCode, Graphify, model manifests, Compose, Windows launchers, performance settings, tests, documentation, or architecture—even for a seemingly small config edit. Enforces canonical boundaries, evidence-first optimization, ADRs, and complete quality gates.
compatibility: Requires the AI Station repository, Git, Python, Bash, Docker Compose for config validation, and optional Graphify for code relationships.
---

# AI Station Engineering

## Establish the baseline

Read `CONTRIBUTING.md`, then the canonical documents relevant to the change:

- `docs/ARCHITECTURE.md` for boundaries and flows;
- `docs/PLATFORM.md` for the application API;
- `docs/ops/AI_STATION_CURRENT_STATE.md` for verified capability;
- accepted ADRs for trade-offs;
- `docs/README.md` for documentation ownership.

Inspect `git status` before editing and preserve unrelated user changes.
For cross-component work, refresh/query Graphify with
`ai graphify extract --code-only` and a narrow relationship question.

## Protect architecture invariants

- llama.cpp stays the primary inference core unless a new accepted ADR and
  benchmark explicitly replace it.
- LiteLLM `http://127.0.0.1:4000/v1` is the only client API.
- Heavy runtime ports and `:8888` remain internal.
- One heavy GPU model at a time; admission precedes lifecycle mutation.
- Model binaries never enter Git and production sources use immutable
  revisions plus SHA-256.
- Host/published endpoints remain loopback-only.
- Docker Compose is the sole supported container runtime.

## Make changes in vertical slices

1. Reproduce or state the current behavior.
2. Identify the authoritative config/code rather than patching generated
   output.
3. Record a new ADR when the change selects a technology, moves a boundary,
   changes compatibility, or adds meaningful operational burden.
4. Implement the smallest coherent slice across code, configuration,
   tests, docs, and rollback.
5. Keep dry-run behavior for resource/destructive operations.
6. Update `CURRENT_STATE` only for verified current facts; put chronology in
   `CHANGELOG.md` and experiments in `docs/research/`.

## Optimize from evidence

Do not raise context, concurrency, GPU layers, or memory limits by intuition.
Capture comparable load time, prompt/generation throughput, peak VRAM/RAM,
quality/tool contracts, and failure behavior. Keep the incumbent as rollback.

## Test strategy

Add unit tests for pure decisions and message transforms; contract tests for
cross-file names, endpoints, capabilities, Windows templates, and safety
guards; live probes only for behavior that mocks cannot establish.

Run, in order:

~~~bash
./scripts/test.sh
make check
ai verify                 # when runtime behavior changed
./scripts/release-audit.sh # release candidate
git diff --check
~~~

Do not weaken checks to make a build green. If a live probe fails, align the
advertised capability with evidence rather than documenting wishful support.

## Completion report

Report the outcome, key files changed, exact gates run, live evidence when
applicable, preserved rollback, and remaining measured limitations.
