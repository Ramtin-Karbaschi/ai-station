# ADR-025: Maximum practical Qwen3.8 context on this GPU

- Status: Accepted
- Date: 2026-08-27

## Context

Qwen3.8 27B reports native `n_ctx_train` of 262144. The live general
profile was still serving 8192 because no workstation probe had proven a
higher window. The operator requirement is to attempt 262144 first, then
131072, with Flash Attention and the highest-quality KV cache that fits.

## Options

1. Advertise 262144 without a live probe.
2. Probe 262144 (Q8 KV, then Q4 KV), then 131072, and keep the largest
   stable window actually measured on this RTX 5090 Laptop.
3. Leave 8192 permanently.

## Decision

Option 2, measured 2026-08-27 on this RTX 5090 Laptop (24463 MiB):

- 262144 + Q8 KV: server started (`n_ctx` 262144, 23967 MiB used) but a
  long ingest hit a 300s HTTP timeout.
- 262144 + Q4 KV + flash-attn: server started (22401 MiB used, 1737 MiB
  free). 23150-token ingest 73.6 s; **138801-token ingest 190.4 s**,
  reply `ctx-ok`. JSON:
  `benchmarks/results/20260827/qwen38-262144-q4-ingest-128k.json`.

Production general/reasoning therefore use **262144** context and **Q4**
KV. OpenCode advertises 262144 for Qwen3.8 only. Ornith/coder stay at
their last measured 8192.

## Consequences

- Docs and OpenCode must not claim 128K/256K until the probe JSON shows
  start + ingest success.
- Vision may land below general because mmproj uses extra VRAM.

## Rollback

Set `LLM_GENERAL_CONTEXT=8192` and recreate `llm-general`.
