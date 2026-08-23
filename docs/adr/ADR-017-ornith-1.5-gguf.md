# ADR-017: Replace Ornith 1.0 GGUF with Ornith 1.5 in the Optional Profile

- Status: Accepted (amended 2026-08-23)
- Date: 2026-08-22
- Supersedes weight pin in [ADR-008](ADR-008-optional-ornith-heavy-profile.md)

## 2026-08-23 amendment

Ornith 1.5 is a retained operator model: never experimental and never
deleted. Coder remains the OpenCode default.

## Context

The operator asked to replace the optional Ornith 1.0 35B GGUF with
[Ornith 1.5 35B-A3B](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B)
(MIT, MoE ~35B / ~3B active). Official serve recipes are vLLM >= 0.19.1
or SGLang >= 0.5.9 on large multi-GPU hosts. This station retains
llama.cpp as the chat engine (ADR-002, ADR-003) and already loads
Ornith 1.0 `qwen35moe` GGUF on the pinned llama.cpp digest.

The official llama.cpp/Ollama artifact is
`ornith-ai/Ornith-1.5-35B-A3B-GGUF`, file `Ornith-1.5-35B-Q4_K_M.gguf`
(~21.7 GB). That is the same size class as Ornith 1.0 Q4_K_M (~21.2 GB)
on this 24 GiB RTX 5090 Laptop. Q5/Q6/Q8/BF16 and the vision mmproj are
out of scope for this profile.

## Options considered

1. Keep Ornith 1.0; ignore 1.5.
2. Promote vLLM or SGLang to serve 1.5 BF16/AWQ.
3. Replace the 1.0 GGUF in the existing optional `ornith` llama.cpp
   profile with 1.5 Q4_K_M. Coder stays the production default.

## Evidence

- GGUF architecture metadata is `qwen35moe`, the same family Ornith 1.0
  already loaded on digest
  `sha256:13f61752307fc4b96c8607a1bc03f977a2a27a4372d194f2aead83d60b964289`.
- File size 21 713 462 848 bytes at immutable revision
  `fbbaed45c2f0e200276ffa51701a24d45dc7f57e`, SHA-256
  `ca6ea26329c88b78ffd90a85163be2e746c2fafd1024f56db47e499f117f9a7f`.
- Community / vendor quality numbers are directional only. No local
  apples-to-apples benchmark versus coder or Ornith 1.0 exists yet under
  `benchmarks/results/`.
- 1.5 is a reasoning model (`<think>` / `reasoning_content`). ADR-009
  required `--reasoning off` so OpenCode did not receive empty `content`.
  Station keeps that flag and `/no_think` until a live OpenCode tool
  probe says otherwise.

## Decision

Adopt option 3.

- Compose/CLI profile remains `ornith`; service `llm-ornith` on
  `127.0.0.1:8086`; alias `local-ornith`.
- Catalog id: `ornith-1_5-35b`
- Public id: `Ornith-1.5-35B-Q4_K_M`
- Manifest id: `ornith-1.5-35b-q4`
- Destination:
  `models/ornith/ornith-1.5-35b-q4_k_m.gguf`
- Provider classification stays `optional_profile`. Do **not** replace
  `coder`. Do **not** bump the llama.cpp image. Do **not** add vLLM or
  SGLang. Do **not** ship the mmproj in this profile.
- Keep `--reasoning off` and `default_system_prefix: /no_think`.
- Ornith 1.0 is **not** a live catalog, LiteLLM, or manifest model.
  The 2026-08-22 operator purge removed the `legacy-ornith-1.0` manifest
  entry and the quarantined 1.0 GGUF. Do not re-download it.

## Consequences

`ai models use ornith` loads 1.5 instead of 1.0. OpenCode, LiteLLM, and
Open WebUI advertise `Ornith-1.5-35B-Q4_K_M`. Coder remains default.

## Risks

- Pinned llama.cpp may still fail a 1.5-specific template or tensor.
  Mitigation: report the load error; keep bytes on disk; do not bump
  the engine without ADR + local benchmark.
- Enabling reasoning may recreate the ADR-009 empty-`content` failure.
  Mitigation: leave `--reasoning off` until a live OpenCode probe.
- Tool quality versus coder is unknown. Mitigation: remain optional.

## Rollback

~~~bash
ai models use coder
# Ornith 1.0 bytes are gone; do not restore them. Keep 1.5 or stop the
# ornith profile.
~~~

## Acceptance criteria

- Catalog, LiteLLM, Open WebUI, and OpenCode expose
  `Ornith-1.5-35B-Q4_K_M` as the ornith public id.
- Manifest pins the 1.5 Q4_K_M file with immutable revision + SHA-256.
- `coder` remains `production_default`.
- `llm-ornith` still binds `127.0.0.1:8086` with `--reasoning off`.
- Load health and a short chat via `:4000` are a separate live smoke;
  this ADR does not claim those passed at merge time.
