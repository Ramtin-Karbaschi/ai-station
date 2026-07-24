# Retrieval evaluation harness (Phase 4)

Public-safe corpus and metric harness for comparing the incumbent retrieval
path before any specialist engine is introduced.

## Metrics

- Recall@K
- MRR
- nDCG
- query / eval latency
- index size (when embedding-backed)
- ingestion time (when embedding-backed)
- failure behavior

## Corpus

`benchmarks/datasets/retrieval/public_safe_v1.json` — synthetic public-safe
documents only. Do not add private documents.

## Runner

~~~bash
python3 benchmarks/runners/run_retrieval_eval.py \
  --out benchmarks/results/YYYYMMDD/retrieval/lexical-public-safe-v1.json
~~~

The current committed baseline is a **lexical** ranking harness. It does not
install Qdrant. An embedding-backed pgvector measurement can reuse the same
corpus once an offline index dump or Open WebUI collection fixture is
available.

## Decision gate (ADR-005)

Retain pgvector as production default unless a measured gap on this corpus
(or a larger public-safe corpus) justifies an optional Qdrant profile.
