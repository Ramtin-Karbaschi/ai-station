# ADR-024: Embedding 8B (4096-d) and official reranker 4B Q6_K

- Status: Accepted
- Date: 2026-08-27
- Amends: [ADR-005](ADR-005-retrieval-engine.md),
  [ADR-022](ADR-022-cpu-embedder-coexistence.md)

## Context

Retrieval quality, not size, drove the upgrade from Qwen3 Embedding /
Reranker 0.6B to Embedding 8B Q4_K_M and Reranker 4B Q6_K.

## Evidence (2026-08-27)

- Embeddings: `/v1/embeddings` returns length **4096**. Manifest SHA-256
  `3fcd3febec8b3fd64435204db75bf0dd73b91e8d0661e0331acfe7e7c3120b85`.
- Open WebUI `document_chunk` was rebuilt from `vector(1536)` to
  `vector(4096)` (67 chunks, 1 Knowledge collection). Backup:
  `/srv/ai-station/backups/document_chunk-20260827T080224Z.sql`.
  A cosine probe for "Station notebook smoke loopback binding" returned
  the smoke fixture at ~0.64. pgvector HNSW/IVFFlat cannot index >2000-d;
  this workstation uses exact cosine scan (acceptable at 67 rows).
- QuantFactory 4B GGUF produced garbage scores (~1e-18) and ranked a
  Paris distractor above the loopback passage.
- Official conversion: `Qwen/Qwen3-Reranker-4B` revision
  `22e683669bc0f0bd69640a1354a6d0aebcfeede5` through llama.cpp
  `4fc4ec5541b243957ae5099edb67372f8f3b550e` `convert_hf_to_gguf.py`
  then `llama quantize Q6_K`. SHA-256
  `33e92e5d354031bbf370894dd30a447c6368ec0f7b70e5810424f5925aec7384`
  (3 305 699 168 bytes). Live `/v1/rerank` ordered the loopback-binding
  passage (0.0067) above cake and Paris distractors.

## Decision

1. Keep the 8B embedder as production CPU default.
2. Serve the official-conversion 4B Q6_K reranker on `:8091`.
3. Delete the 0.6B reranker after that ranking probe.
4. Rerankers stay out of the document-OCR pipeline (ADR-006).

## Rollback

Re-run `scripts/convert-qwen3-reranker-4b.sh`. Knowledge restore is
independent.

## Acceptance criteria

- All Knowledge collections query-only against 4096-d rows.
- Reranker orders gold passages above distractors on a station fixture
  set before 0.6B rerank bytes are deleted.
