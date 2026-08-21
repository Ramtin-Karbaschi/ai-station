# ADR-011: OpenCode Context Ceiling — Quantized KV Cache Headroom Evaluation

- Status: Accepted
- Date: 2026-08-19

## Context

This is the hardware track of the OpenCode task-loss work. The behavioral
track (lossy native compaction dropping part of a multi-step request) is
owned by ADR-009 and ADR-013. This ADR asks a separate question:
does any real VRAM headroom exist to raise the OpenCode context ceiling
above the current 8192-token default (`LLM_CODER_CONTEXT`,
`LLM_ORNITH_CONTEXT`, etc. in `.env.models`, default `8192` in
`compose.models.yml`), given that
`docs/adr/ADR-004-resource-admission-control.md` already measured only
507 MiB of free VRAM headroom on this exact RTX 5090 Laptop (24463 MiB)
with the `general` profile loaded at 8192 context, f16 KV cache, and
stated that "a single context increase from 8K to 16K on the general
model would exceed it."

Per the station benchmark policy, any proposed
change requires a local, apples-to-apples benchmark under
`benchmarks/results/`, a documented promotion threshold of >= 20%
improvement in the primary metric with no quality regression, and an
ADR either way (a decision to retain the current architecture is
explicitly a valid outcome).

**Primary metric for this decision**: usable context ceiling (tokens)
before OpenCode's auto-compaction fires, for a given heavy profile,
while keeping >= 1 GiB free-VRAM safety margin (the existing ADR-004
policy default) and no observed tool-calling/coherence regression in a
short smoke test.

Research into the only realistic lever — llama.cpp's quantized KV
cache (`--cache-type-k` / `--cache-type-v`) — is recorded in
`docs/research/TECHNOLOGY_EVALUATION_MATRIX.md` (2026-08-19 addendum).
Summary: the exact pinned image
(`ghcr.io/ggml-org/llama.cpp@sha256:13f61752307fc4b96c8607a1bc03f977a2a27a4372d194f2aead83d60b964289`,
version b9859, revision `4fc4ec5541b243957ae5099edb67372f8f3b550e`,
built 2026-07-02) supports `q8_0`/`q4_0`/etc. KV cache types (confirmed
by running `--help` against the pinned image directly on this host);
symmetric `q8_0/q8_0` is reported as near-lossless and is the only
combination that avoids a confirmed CPU-fallback bug affecting
asymmetric K/V type combinations (ggml-org/llama.cpp Issue #20866).

## Options considered

1. Leave the 8192 default unchanged for all profiles (status quo).
2. Raise the context default uniformly for all heavy profiles
   (general/coder/reasoning/vision/ornith) with quantized KV cache.
3. Raise the context default only for the specific profile(s) where a
   local benchmark shows a safe margin, and explicitly retain 8192 for
   the rest, based only on measured per-profile VRAM headroom.

## Evidence

All commands were run on this host (RTX 5090 Laptop, 24463 MiB total
VRAM) using the pinned image digest above. Full structured results:
`benchmarks/results/20260819/opencode-context/`.

### Coder profile (`Qwen3-Coder-30B-A3B-Instruct-Q4`, ~17.6 GiB GGUF)

| Config | File | Free VRAM (MiB) | Status | Smoke test |
|---|---|---|---|---|
| `-c 8192`, f16 KV (live default) | `coder-baseline-c8192-f16.json` | 3461 | healthy | `ai opencode test --model coder`: pong + `get_time` tool call OK |
| `-c 8192`, `--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on` | `coder-quantkv-c8192-q8_0.json` | 3815 (+354) | healthy | direct curl: pong + tool call OK |
| `-c 12288`, same quantized KV | `coder-quantkv-c12288-q8_0.json` | 3613 | healthy, no OOM/crash | pong + tool call + 3-turn tool-result follow-up all coherent |
| `-c 16384`, same quantized KV | `coder-quantkv-c16384-q8_0.json` | 3404 | healthy, no OOM/crash | pong + tool call + 3-turn follow-up all coherent |

Coder already has far more baseline headroom (3461 MiB free at the
live 8192/f16 default) than the ADR-004 507 MiB figure, because its
GGUF file (~17.6 GiB) is smaller than `general`/`ornith` (~21-22 GiB).
Doubling context to 16384 with `q8_0/q8_0` KV cache still left 3404
MiB free — well above the 1 GiB safety margin — with no observed OOM,
crash, healthcheck failure, or tool-calling/coherence regression across
three separate smoke tests (short reply, single tool call, and a
synthetic multi-turn tool-result follow-up).

Primary-metric improvement for coder: 8192 -> 16384 tokens = **+100%**,
clearing the >= 20% promotion bar, with no quality regression observed
and a 3404 MiB safety margin (> 1 GiB policy floor).

### Ornith profile (`Ornith-1.0-35B-Q4_K_M`, ~21.2 GiB GGUF)

| Config | File | Free VRAM (MiB) | Status | Smoke test |
|---|---|---|---|---|
| `-c 8192`, f16 KV (live default) | `ornith-baseline-c8192-f16.json` | 761 | healthy | `ai opencode test --model ornith`: pong + `get_time` tool call OK |
| `-c 8192`, `--cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on` | `ornith-quantkv-c8192-q8_0.json` | 703 (**-58**) | healthy | direct curl: pong + tool call OK |

For ornith, quantized KV cache produced **no net VRAM gain** — free
VRAM was actually ~58 MiB *lower* than the f16 baseline (within
measurement noise of "flat", not a real improvement). This null/
slightly-negative result is explained by two things stacking against
the small KV cache saving at only 8192 tokens: (1) the KV cache itself
is a very small fraction of a ~21.2 GiB model's VRAM footprint at this
context length, so halving it saves little in absolute MiB, and (2)
forcing `--flash-attn on` (required to get any benefit from, and avoid
CPU-fallback with, quantized KV — see the research addendum) adds its
own CUDA compute-buffer overhead that roughly cancels the small KV
saving for this model/context combination.

Because this did not free meaningfully more than the reference 507 MiB
headroom figure (it froze nothing), the benchmark plan's own
precondition for attempting a raised context (12288/16384) was not
met, and elevated-context testing was **not attempted for ornith** —
doing so from a starting point of less headroom than the
already-insufficient 507 MiB case would be expected to OOM and was not
worth the additional live-GPU disruption on this shared, currently-serving
GPU to demonstrate.

Primary-metric improvement for ornith: **0%** (no safe increase found).
Does not clear the >= 20% bar.

### Not tested

`general`, `reasoning`, and `vision` profiles were out of this task's
scope (only `coder` and `ornith` — the two models OpenCode actually
uses by default and via its Ornith picker option — were benchmarked).
`general` is architecturally close in weight-file size to `ornith`
(~22.1 GiB vs. ~21.2 GiB) and ADR-004 already measured only 507 MiB
free headroom for it at the current default; by that similarity it is
plausible (not measured) that `general` would show the same
"no meaningful gain" pattern as `ornith`, but this ADR does not claim
that as evidence — it remains "requires benchmark" if a future
decision needs it.

## Decision

Adopt option 3, split by profile, based only on what was measured:

- **Coder**: the evidence supports a safe context increase. Status:
  **Accepted — applied on 2026-08-19**. The following files were
  changed to apply it:
  - `.env.models` and `.env.models.example`: `LLM_CODER_CONTEXT=8192`
    -> `16384`.
  - `.env` and `.env.example`: added `LLM_CODER_CONTEXT=16384`. This
    step was **not** in the original recommendation above but proved
    required during live verification: `docker compose` interpolates
    `${LLM_CODER_CONTEXT}` in `compose.models.yml` from the root `.env`
    file (`--env-file .env` in `scripts/compose-ai-station.sh`), not
    from `.env.models`'s `env_file:` block (that only injects env vars
    into the container's own process, which llama.cpp's CLI-flag-based
    command list never reads). Without mirroring the value into `.env`,
    the container silently kept using `compose.models.yml`'s own
    `8192` fallback despite `.env.models` saying `16384` — confirmed
    live via `docker compose config` and the running container's
    `n_ctx_slot` log line before and after this fix.
  - `compose.models.yml`: added `--cache-type-k q8_0 --cache-type-v
    q8_0 --flash-attn on` to the `llm-coder` service command.
  - `config/clients/opencode/opencode.jsonc.template`: the
    `Qwen3-Coder-30B-A3B-Instruct-Q4` model's `limit.context` `8192` ->
    `16384` (the other three models are unchanged).
  - `tests/test_opencode_client_contract.py`: per-model expected
    context values (coder=16384, the other three=8192) instead of a
    flat `8192` assertion.
  - Verified live: `./scripts/ai models use coder` +
    `./scripts/ai opencode test --model coder` both healthy;
    `docker logs ai-station-llm-coder` shows `n_ctx_slot = 16384`; GPU
    free VRAM after load was `5035 MiB` (healthier than this ADR's own
    `3404 MiB` scratch-benchmark figure at the same context/KV
    settings, no OOM/crash); GPU was restored to the pre-task profile
    afterward.
- **Ornith**: the evidence does **not** support a safe context
  increase. Decision: **retain the current 8192 default; rejected due
  to hardware VRAM limits**, per the measured 703 MiB (quantized) vs.
  761 MiB (f16 baseline) free-VRAM figures above — both far below the
  1 GiB safety margin, and the quantized-KV lever produced no usable
  gain to build a higher context on top of.
- **General / reasoning / vision**: no change; not benchmarked in this
  task; the existing ADR-004 8K figure and policy continue to apply
  unchanged.

This ADR intentionally does not force a uniform answer across all
profiles — the measured VRAM headroom differs by GGUF file size, and
the two profiles this task was scoped to test came out on opposite
sides of the promotion bar.

## Consequences

- **Coder**: behavior changed on 2026-08-19. `coder` now runs with
  16384 context and quantized (`q8_0/q8_0`) KV cache with flash
  attention on; see the file list in the Decision section above.
  OpenCode's compaction pressure for coder-driven sessions should
  measurably ease (more raw tokens available before the tool-schema
  overhead forces a compaction), independent of and complementary to
  the Track A verbatim-request fix.
- Quantized KV cache quality for coder is still only verified against
  the short smoke tests described in Evidence above, not a first-party
  perplexity benchmark; keep monitoring real session behavior.
- Ornith-driven OpenCode sessions remain exactly as constrained as
  today (unchanged, 8192); Track A's compaction fix is the only
  mitigation available to them.
- General, reasoning, and vision profiles are unchanged (still 8192,
  f16 KV cache); this ADR did not benchmark or touch them.

## Risks

- The 3404 MiB margin measured for coder at 16384/q8_0 is a short
  smoke-test snapshot, not a long-running, multi-hour, concurrent-load
  measurement. Real OpenCode sessions with longer tool-call histories
  could still approach the ceiling differently than this benchmark's
  short prompts did. Mitigation: any follow-up change should keep
  monitoring headroom via `ai status` / `nvidia-smi` after rollout, not
  rely solely on this one-time benchmark.
- Quantized KV cache quality: no first-party perplexity/quality
  benchmark was run beyond a short "pong" reply and a couple of
  tool-call probes; community sources (cited in the research addendum)
  report `q8_0/q8_0` as near-lossless, but this is directional
  evidence, not a first-party guarantee for Qwen3-Coder-30B-A3B
  specifically.
- `--flash-attn on` is required for the quantized KV path to behave as
  measured; if a future engine image rebuild changes flash-attention
  defaults or kernel availability, these numbers would need
  re-measuring before being relied upon again.
- Any future attempt to raise `general`'s or `ornith`'s context should
  not assume the ornith null result transfers to `general` without its
  own measurement, even though the weight-file sizes are similar.

## Rollback

To revert the applied `coder` change:

```bash
# revert LLM_CODER_CONTEXT to 8192 in .env, .env.example, .env.models,
# .env.models.example; remove --cache-type-k/--cache-type-v/--flash-attn
# from the llm-coder command in compose.models.yml; revert
# opencode.jsonc.template's coder limit.context to 8192; revert the
# per-model EXPECTED_CONTEXT test assertions to a flat 8192.
./scripts/ai models use coder   # relies on the reverted config
```

## Acceptance criteria

- Evaluation phase (unchanged from original): benchmark evidence for
  both tested profiles exists under
  `benchmarks/results/20260819/opencode-context/`: 6 files total, one
  per configuration tested (coder: baseline-8192-f16,
  quantkv-8192-q8_0, quantkv-12288-q8_0, quantkv-16384-q8_0; ornith:
  baseline-8192-f16, quantkv-8192-q8_0). Research findings (flag
  support, version, caveats, sources) are recorded in
  `docs/research/TECHNOLOGY_EVALUATION_MATRIX.md`.
- Application phase (2026-08-19, this update): `.env`, `.env.example`,
  `.env.models`, `.env.models.example`, `compose.models.yml`,
  `opencode.jsonc.template`, and
  `tests/test_opencode_client_contract.py` were all updated per the
  Decision section's file list, and
  `python3 -m unittest tests.test_opencode_client_contract` passes.
- The GPU was returned to the exact profile it was running before this
  work started (`ornith`, confirmed via `ai status` after the final
  restore) with no other live config touched.
- Ornith, general, reasoning, and vision remain at their pre-existing
  8192/f16 configuration; none of their files or defaults were
  changed.
