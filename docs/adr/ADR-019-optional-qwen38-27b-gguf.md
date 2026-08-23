# ADR-019: Optional Qwen3.8-27B GGUF Profile

- Status: Accepted (amended 2026-08-23)
- Date: 2026-08-22

## 2026-08-23 amendment

Qwen3.8-27B (GGUF + mmproj) is a retained operator model: never
experimental and never deleted. It does not replace `general` or
`vision`.

## Context

The operator asked to download and register
[Qwen/Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B) (Apache-2.0,
native vision-language, tools, thinking on by default). The official
Hugging Face tree is Transformers BF16 safetensors and will not fit this
24 GiB GPU. It also cannot be served by llama.cpp.

This station retains llama.cpp as the chat engine (ADR-002, ADR-003).
The matching GGUF is Unsloth `unsloth/Qwen3.8-27B-GGUF`. Station
convention for a 24 GiB general-class chat model is UD-Q4_K_M.

Qwen3.8 is dense ~27B `qwen35` (Gated DeltaNet hybrid), not a drop-in
replacement for `general` (Qwen3.6 35B MoE text) or `vision`
(Qwen3-VL-32B, no tools).

## Options considered

1. Download official BF16 safetensors and serve with SGLang/vLLM.
2. Replace `general` or `vision` with Qwen3.8 GGUF.
3. Add an optional llama.cpp heavy profile with Unsloth UD-Q4_K_M plus
   `mmproj-F16.gguf`. Do not change production defaults.

## Evidence

- Official card: Apache-2.0, image-text-to-text, architecture Qwen3.5 /
  `qwen35`, thinking on by default. Fetched 2026-08-22.
- Unsloth revision `4ca720788d1e01f1bff70c033e0d0028fd02e502`
  (lastModified 2026-08-20):
  - `Qwen3.8-27B-UD-Q4_K_M.gguf` 16 464 440 224 bytes, SHA-256
    `322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482`
  - `mmproj-F16.gguf` 927 607 488 bytes, SHA-256
    `cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e`
- Combined weights ~16.2 GiB, below the 22 GiB `general` GGUF, so 8192
  context is the starting budget. Live VRAM remains a smoke, not a claim.
- Pinned llama.cpp OCI `b9859` (digest
  `sha256:13f61752307fc4b96c8607a1bc03f977a2a27a4372d194f2aead83d60b964289`,
  built 2026-07-02) already contains `llama_model_qwen35` and
  `graph_mtp`. The station already loads Qwen3.6 (`qwen35moe`) on this
  digest. This ADR does **not** bump the image. If Unsloth's August GGUF
  fails to load, keep the bytes, report the error, and write a follow-up
  ADR before changing `compose.images.lock.yaml`.
- Community notes that some Qwen3.8 GGUFs want later builds (b10355+)
  are directional only.
- No local apples-to-apples benchmark versus `general` or `vision`
  exists yet under `benchmarks/results/`.

## Decision

Adopt option 3.

- Compose/CLI profile: `qwen38`
- Service: `llm-qwen38` on `127.0.0.1:8087`
- Alias: `local-qwen38`
- Catalog id: `qwen38-27b`
- Public id: `Qwen3.8-27B-UD-Q4_K_M`
- Manifest ids: `qwen38-27b-q4`, `qwen38-27b-mmproj-f16`
- Destinations:
  - `models/qwen38/qwen3.8-27b-ud-q4_k_m.gguf`
  - `models/qwen38/mmproj-f16.gguf`
- Provider `llama-cpp-qwen38`, classification `optional_profile`.
- Do **not** replace `general`, `coder`, or `vision`.
- Do **not** download official BF16 safetensors.
- Do **not** add SGLang or vLLM.
- Do **not** bump llama.cpp for other profiles.
- Thinking stays enabled (no `--reasoning off`, no `/no_think`). The
  host gateway already copies empty `content` from `reasoning_content`
  (ADR-009 mitigation). This profile is not an OpenCode default.
- Include the F16 mmproj so native vision is available. OpenCode's
  curated picker stays unchanged until a live tool+vision probe.

## Consequences

`ai models use qwen38` loads Unsloth Qwen3.8-27B UD-Q4_K_M with mmproj.
LiteLLM, Open WebUI, and the host gateway advertise
`Qwen3.8-27B-UD-Q4_K_M`. Coder remains the OpenCode default. General
remains the default heavy chat profile.

## Risks

- Pinned llama.cpp may reject a newer Unsloth tensor or vision key.
  Mitigation: report the load error; keep bytes; do not bump the engine
  without a follow-up ADR plus a smoke that `general` still loads.
- Thinking may still confuse some clients. Mitigation: optional profile;
  gateway flatten; not the OpenCode default.
- Quality versus `general` / `vision` is unknown. Mitigation: remain
  optional until a local benchmark.

## Rollback

~~~bash
ai models use general
# Bytes stay on disk. Quarantine with:
# ai models remove qwen38-27b-q4 --confirm
# ai models remove qwen38-27b-mmproj-f16 --confirm
~~~

## Acceptance criteria

- Catalog, LiteLLM, and Open WebUI expose `Qwen3.8-27B-UD-Q4_K_M`.
- Manifest pins both GGUF files with immutable revision + SHA-256.
- `general` and `coder` remain `production_default`.
- `llm-qwen38` binds `127.0.0.1:8087` only, same digest-pinned llama.cpp
  image as the other heavy profiles.
- Load health and a short chat via `:4000` are a separate live smoke;
  this ADR does not claim those passed at merge time.
