# ADR-026: Delete superseded model bytes after acceptance

- Status: Accepted
- Date: 2026-08-27

## Context

Quality-first upgrades leave old GGUFs on disk until replacements pass
acceptance. Permanent quarantine wastes NVMe and invites stale aliases.

## Decision

After a replacement is checksum-verified, integrated, and accepted:

1. Record path, size, SHA-256, replacement id, and evidence.
2. Remove catalog, LiteLLM, provider, and manifest runtime entries.
3. Delete the old file and safe Hugging Face cache objects.
4. Search the repo so no runtime config still names the old model.

Historical ADRs and benchmark JSON may keep old names.

Retained forever: Ornith 1.5, Qwen3.8, LongWriter-Zero Q4, ComfyUI
MiniMax Music 3 / H3 / FLUX.2-dev.

## Consequences

Qwen3.6, Qwen3-Coder 30B, DeepSeek-R1 Distill Qwen 32B, and Qwen3-VL-32B
plus mmproj are already gone from `/srv`. Embedding/reranker 0.6B files
wait until RAG reindex and rerank quality acceptance.
