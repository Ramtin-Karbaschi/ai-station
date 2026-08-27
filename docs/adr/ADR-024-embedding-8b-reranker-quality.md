# ADR-024: Embedding 8B (4096-d) and reranker 4B with quality gate

- Status: Accepted for embedding bytes; reranker conversion **not accepted**
- Date: 2026-08-27
- Amends: [ADR-005](ADR-005-retrieval-engine.md),
  [ADR-022](ADR-022-cpu-embedder-coexistence.md)

## Context

Retrieval quality, not size, drove the upgrade from Qwen3 Embedding /
Reranker 0.6B to Embedding 8B Q4_K_M and Reranker 4B Q6_K. Both new
files are on disk, SHA-256-matched, and loaded on CPU `:8090` / `:8091`.

## Evidence (2026-08-27)

- Embeddings: `/v1/embeddings` returns length **4096**. Manifest SHA-256
  `3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85`.
- Open WebUI `document_chunk` was rebuilt from `vector(1536)` to
  `vector(4096)` (67 chunks, 1 Knowledge collection). Backup:
  `/srv/ai-station/backups/document_chunk-20260827T080224Z.sql`.
  A cosine probe for "Station notebook smoke loopback binding" returned
  the smoke fixture at ~0.64. pgvector HNSW/IVFFlat cannot index >2000-d;
  this workstation uses exact cosine scan (acceptable at 67 rows).
- Reranker: `/v1/rerank` HTTP 200, `n_params` 4.41B, SHA-256
  `1cf491b95e4d622306a5e1deff25cb9f2deeedd83fc2149b17f450d2587c2269`.
  Relevance scores on a loopback/API query were ~1e-18–1e-30 and ranked
  "The capital of France is Paris" above the loopback-binding passage.
  QuantFactory GGUF is a community conversion, not official Qwen.

## Decision

1. Keep the 8B embedder as production CPU default.
2. Rebuild every Open WebUI Knowledge collection at 4096-d before
   deleting `qwen3-embedding-0.6b-q8_0.gguf`. Never mix widths in
   pgvector.
3. Do not accept the live 4B reranker for RAG quality. Convert from
   official `Qwen/Qwen3-Reranker-4B` with `convert_hf_to_gguf.py`, or
   keep serving 0.6B until an apples-to-apples ranking probe wins.
4. Rerankers stay out of the document-OCR pipeline (ADR-006).

## Rollback

Point Compose at the 0.6B filenames, recreate embedder/reranker, restore
Knowledge from backup if a mixed-dimension write occurred.

## Acceptance criteria

- All Knowledge collections query-only against 4096-d rows.
- Reranker orders gold passages above distractors on a station fixture
  set before 0.6B rerank bytes are deleted.
