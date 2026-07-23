# Retrieval evaluation harness (Phase 4 scaffold)

Public-safe corpus and metric placeholders for comparing pgvector against a
specialist engine later. No production migration is performed here.

## Planned metrics

- Recall@K
- MRR
- nDCG
- query latency
- index size
- ingestion time
- failure behavior

## Corpus

Use only public-safe documents under `benchmarks/datasets/retrieval/` (to be
populated before Phase 4 execution). Do not add private documents.
