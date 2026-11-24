# ADR-023: Qwen3.8 and Ornith 1.5 become production chat defaults

- Status: Accepted (implementation in progress; LiteLLM key migration and
  RAG reindex still open)
- Date: 2026-08-27
- Amends: [ADR-017](ADR-017-ornith-1.5-gguf.md),
  [ADR-019](ADR-019-optional-qwen38-27b-gguf.md),
  [ADR-008](ADR-008-optional-ornith-heavy-profile.md)

## Context

The station replaced Qwen3.6 35B MoE (general), Qwen3-Coder 30B (coder),
DeepSeek-R1 Distill 32B (reasoning), and Qwen3-VL-32B (vision) with:

- Qwen3.8 27B UD-Q4_K_M + mmproj for general, reasoning, and vision;
- Ornith 1.5 35B-A3B Q4_K_M for coder / OpenCode.

Those four superseded GGUFs are deleted from `/srv`. Ornith, Qwen3.8,
LongWriter-Zero Q4, MiniMax Music 3, MiniMax H3, and FLUX.2 remain
retained operator packs and must never be deleted.

## Options considered

1. Keep Qwen3.8 and Ornith as optional profiles only (ADR-017/019).
2. Promote them to production defaults and delete the superseded bytes.
3. Run both old and new heavy GGUFs in parallel.

## Evidence

- Host gateway `:8888` advertises the new canonical public names
  (2026-08-27).
- llama.cpp `:8082` reports `n_params` 27.3B, `n_ctx_train` 262144,
  `n_ctx` 8192, and completed a 16-token `general-ok` probe.
- Optional `llama-cpp-ornith` / `llama-cpp-qwen38` stay as compatibility
  aliases so rollback of *routing* does not require a second copy of the
  same bytes. Do not start two heavy containers that load the same file.

## Decision

Option 2. Catalog, LiteLLM YAML, Compose model files, and OpenCode
template use Qwen3.8 and Ornith 1.5 as production defaults.

Context stays at the last measured 8192 until a live 131072 then 262144
probe on this GPU records VRAM, prefill, decode, and a retrieval check.
Do not advertise 32K/128K from `n_ctx_train` alone.

## Consequences

- LiteLLM virtual keys created against the old public names 403/400 until
  `ai projects update`.
- ADR-017 and ADR-019 sentences that say Qwen3.8/Ornith do not replace
  general/coder are superseded by this ADR.
- Duplicate Compose profiles `ornith` and `qwen38` remain optional
  aliases, not a second production default.

## Rollback

Restore superseded GGUFs from backup/quarantine, revert catalog and
`litellm.yaml`, regenerate project keys, `ai models use general`.

## Acceptance criteria

- `ai projects` keys can call the new public names.
- `make check` and `scripts/release-audit.sh` pass with Errors 0 /
  Warnings 0.
- No client targets `:8888` or llama.cpp ports.
