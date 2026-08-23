# ADR-008: Optional Ornith Heavy llama.cpp Profile

- Status: Accepted
- Date: 2026-08-18
- Weight pin superseded 2026-08-22 by
  [ADR-017](ADR-017-ornith-1.5-gguf.md) (same `ornith` profile;
  GGUF is now Ornith 1.5 Q4_K_M). Topology in this ADR is unchanged.
- 2026-08-23: Ornith is a retained operator model — never experimental
  and never deleted. Coder remains the OpenCode default.

## Context

AI Station already has four production heavy llama.cpp profiles
(`general`, `coder`, `reasoning`, `vision`) with a hard rule of at most
one heavy GPU provider at a time. Ornith-1.0-35B Q4_K_M is a ~21 GB GGUF
in the same size class as the current general model, offered as an
additional agentic-coding candidate. The incumbent coder profile
(`Qwen3 Coder 30B`) is in production use and must not be replaced without
a local apples-to-apples benchmark.

MiniMax-H3 is out of scope (not a chat model; official weights are far
larger than this workstation).

## Options considered

1. Do not add Ornith; keep the four production heavy profiles.
2. Replace the `coder` profile with Ornith.
3. Add Ornith as a fifth **optional** heavy llama.cpp profile (`ornith`),
   switched serially via `ai models use ornith`, without changing the
   one-heavy GPU policy or the production coder default.

## Evidence

- File size is ~21.2 GB, comparable to the current general GGUF on a
  24 GiB RTX 5090 Laptop; VRAM fit is therefore plausible at 8K context
  but is **not** a measured local benchmark.
- No local quality, latency, or tool-calling benchmark versus `coder`
  exists yet under `benchmarks/results/`. Community numbers are
  directional only.
- llama.cpp architecture support for `qwen35moe` in the currently pinned
  digest (`sha256:13f61752307fc4b96c8607a1bc03f977a2a27a4372d194f2aead83d60b964289`)
  is **unknown** until a load smoke-test. The engine digest is not bumped
  in this ADR.

## Decision

Adopt option 3.

- Compose/CLI profile: `ornith`
- Service: `llm-ornith` on `127.0.0.1:8086`
- Alias: `local-ornith`
- Catalog id: `ornith-1_0-35b`
- Manifest id: `ornith-1.0-35b-q4`
- Provider: `llama-cpp-ornith`, classification `optional_profile`,
  `experimental: false`, `heavy: true`, fallback `llama-cpp-general`
- Do **not** replace `coder` / `llama-cpp-coder`
- Do **not** change `max_active_heavy` / one-heavy GPU policy
- Do **not** bump the llama.cpp image digest
- Promotion to production default requires a local benchmark (≥20%
  primary-metric improvement, no quality regression) and a follow-up ADR

## Consequences

Operators can switch Ornith in the same serial queue as the other heavy
profiles. LiteLLM, the UI gateway, and Open WebUI model_ids gain
`local-ornith`. Admission treats it as another heavy provider and will
stop a conflicting heavy profile before start.

## Risks

- The pinned llama.cpp server may fail to load `qwen35moe` weights.
  Mitigation: report the load error; keep the GGUF on disk; do not bump
  the engine without ADR + local benchmark.
- VRAM/KV-cache at 8K may still OOM on this 24 GiB GPU. Mitigation:
  admission `minimum_vram_mib: 21000` plus the existing safety margin;
  rollback to general.
- Tool-calling quality may be worse than `coder`. Mitigation: remain
  optional until benchmarked.

## Rollback

~~~bash
ai models use general
~~~

Leave the optional profile, catalog entry, and weights in place. To
remove the profile entirely, delete the `llm-ornith` Compose service and
registry entries in a follow-up change; weights stay under
`/srv/ai-station/models/ornith` until an approved delete.

## Acceptance criteria

- `ai models use ornith` is a recognized heavy profile and stops any
  other heavy profile first.
- `llm-ornith` binds `127.0.0.1:8086` only and uses the same llama.cpp
  digest as `llm-coder`.
- Provider classification is `optional_profile`; `coder` remains
  production default.
- Dry-run admission for `llama-cpp-ornith` explains the one-heavy
  decision.
- Load healthcheck and a short chat via `:4000` / `local-ornith` are
  owned by a separate smoke-test; this ADR does not claim those passed.
