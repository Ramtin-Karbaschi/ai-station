# ADR-020: Optional LongWriter-Zero-32B Profile

- Status: Accepted (amended 2026-08-23)
- Date: 2026-08-23

## Operator retention (same day)

LongWriter-Zero Q4 is a retained operator model: never experimental and
never deleted. It does not replace `general`.

## Context

The operator asked to keep
[mradermacher/LongWriter-Zero-32B-GGUF](https://huggingface.co/mradermacher/LongWriter-Zero-32B-GGUF)
as an 8-bit GGUF for reinforcement-learning / long-form writing work.
The upstream model is [THU-KEG/LongWriter-Zero-32B](https://huggingface.co/THU-KEG/LongWriter-Zero-32B)
(Apache-2.0, Qwen2.5-32B fine-tune). mradermacher publishes static GGUF
quants. The originally requested 8-bit file is
`LongWriter-Zero-32B.Q8_0.gguf`.

This 24 GiB GPU cannot hold a 32.4 GiB Q8_0 file plus KV cache with
`-ngl 999`. llama.cpp remains the engine (ADR-002). Official BF16 is
not downloaded.

## Options considered

1. Ignore the request.
2. Download Q4_K_M (~18.5 GiB) because it fits the GPU with `-ngl 999`.
3. Pin Q8_0 with partial GPU offload (`-ngl 40`).
4. Pin Q5_K_M (~21.7 GiB) as the next-higher quant. Rejected: weights
   plus KV at 4096 would leave almost no headroom on 24463 MiB.

## Evidence

- Repo revision `4ed85f5410b2a3c16414e9e36e4b9810ee380fb1`
  (lastModified 2025-07-04):
  - `LongWriter-Zero-32B.Q8_0.gguf` 34 820 885 792 bytes, SHA-256
    `a3d65278939a839055805d6ccf5feae435e6720cfe1db675bf4af12d812ff625`
  - `LongWriter-Zero-32B.Q4_K_M.gguf` 19 851 336 992 bytes, SHA-256
    `b4beb52b144dd8f02f274c3172c642102fe2153cdd0313cae5166ed48c51af67`
  - Architecture metadata on the card is `qwen2` (already supported by
    pinned llama.cpp b9859).
- Live smoke 2026-08-23 on this RTX 5090 Laptop (24463 MiB):
  - Qwen3.8-27B UD-Q4_K_M via LiteLLM `:4000`: identity 1.377 s,
    JSON 2.102 s, tools 2.664 s. VRAM 20100 MiB used. **Pass.**
  - LongWriter Q8_0 with default `-ngl 40`: container healthy; short
    chat via `:4000` returned in 11.8 s at ~2.7 tok/s; VRAM 24030 MiB
    used / 108 MiB free. Unsuitable for RL rollouts on this GPU.
  - LongWriter Q4_K_M with `-ngl 999`: container healthy; LiteLLM
    `:4000` paragraph smoke 5.696 s / 22.47 tok/s (128 tokens);
    host `:8088` short chat 1.212 s / 13.2 tok/s. VRAM 23975 MiB used
    / 163 MiB free. Suitable replacement.
- Q8_0 bytes were quarantined then purged at operator request.

## Decision

Adopt option 2 after the live Q8_0 smoke.

- Compose/CLI profile: `longwriter`
- Service: `llm-longwriter` on `127.0.0.1:8088`
- Alias: `local-longwriter`
- Catalog id: `longwriter-zero-32b`
- Public id: `LongWriter-Zero-32B-Q4_K_M`
- Manifest id: `longwriter-zero-32b-q4`
- Destination: `models/longwriter/longwriter-zero-32b-q4_k_m.gguf`
- Provider `llama-cpp-longwriter`, classification `optional_profile`.
- Default `-ngl` is **999**, default context **8192**.
- Do **not** replace `general`, `coder`, or `reasoning`.
- Do **not** keep Q8_0 on disk. Do **not** bump llama.cpp.

## Consequences

`ai models use longwriter` loads the Q4_K_M GGUF fully on GPU.
LiteLLM and Open WebUI advertise `LongWriter-Zero-32B-Q4_K_M`.
8-bit quality is not available on this workstation.

## Risks

- Q4_K_M is lower fidelity than Q8_0. Mitigation: it is the highest
  recommended quant that actually fits; Q5_K_M is too tight.
- Long-context RL may still need a context bump. Mitigation: raise
  `LLM_LONGWRITER_CONTEXT` only after a live VRAM smoke.

## Rollback

~~~bash
ai models use general
# ai models remove longwriter-zero-32b-q4 --confirm
~~~

Q8_0 is not a rollback path; those bytes were deleted.

## Acceptance criteria

- Catalog, LiteLLM, and Open WebUI expose `LongWriter-Zero-32B-Q4_K_M`.
- Manifest pins Q4_K_M with immutable revision + SHA-256.
- `general` and `coder` remain `production_default`.
- `llm-longwriter` binds `127.0.0.1:8088` only, same digest-pinned
  llama.cpp image, default `-ngl` is 999.
- Live load health and a short chat via `:4000` pass for Q4_K_M.
- Q8_0 GGUF is absent from `/srv/ai-station/models/`.
