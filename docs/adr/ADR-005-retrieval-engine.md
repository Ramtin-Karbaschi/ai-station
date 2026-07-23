# ADR-005: Retrieval Engine — Retain pgvector, Evaluate Before Any Migration

- Status: Proposed
- Date: 2026-07-23

## Context

Open WebUI RAG stores vectors in PostgreSQL/pgvector. Qdrant offers native
hybrid (dense+sparse) retrieval, payload-indexed filtering, and RRF fusion.

## Options considered

1. Retain pgvector only.
2. Migrate retrieval to Qdrant now.
3. Retain pgvector as source of truth; run a Phase 4 retrieval evaluation
   and add Qdrant as an optional profile only if measured gaps matter.

## Evidence

- Corpus scale here is a single user's documents — orders of magnitude
  below the 1-5M-vector region where 2026 comparisons show pgvector
  weakening; network and model latency dominate end-to-end RAG time.
- Qdrant would add a second stateful store, a sync pipeline, and new
  backup surface with no demonstrated local benefit.
- PostgreSQL must stay regardless (Open WebUI + LiteLLM state), so
  pgvector's marginal cost is zero.

## Decision

Adopt option 3. PostgreSQL remains the application source of truth
(users, permissions, metadata, transactions, audit, workflow state). Any
future specialist engine owns only the retrieval index (dense/sparse/
multivector and retrieval-specific filtering). Migration requires the
Phase 4 evaluation: Recall@K, MRR, nDCG, latency, index size, ingestion
time, failure behavior on a public-safe corpus.

## Consequences

- Retrieval quality work in the near term focuses on the existing stack:
  chunking parameters, reranker activation, and hybrid SQL retrieval.

## Risks

- If corpus scale or filtering complexity grows sharply, the evaluation
  must be re-run; the risk of premature migration is higher than the risk
  of waiting.

## Rollback

Not applicable (retains incumbent). A future Qdrant trial must document
index rebuild from Postgres as its rollback path.

## Acceptance criteria

- Phase 4 evaluation report with the metrics above, or an explicit
  decision to keep this ADR as final with pgvector-only.
