# Inference Benchmark Report

Date: 2026-07-23
Status: Phase 1 baseline only. No competing engine has been installed yet.

## Scope

Baseline for production `llama.cpp` general provider
(`ai-station-general`, GGUF Q4_K_M) on the RTX 5090 Laptop under WSL2.

Result file:

~~~text
benchmarks/results/20260723/llama-cpp/general-qwen3.6.json
~~~

## Observed results

| Case | OK | TTFT (ms) | E2E (ms) | Notes |
|---|---|---|---|---|
| short-prompt | yes | 4473 | 4723 | |
| code-generation | yes | 4457 | 35054 | |
| json-schema-like | yes | 4321 | 8112 | |
| context-8k-synthetic | yes | 6000 | 6575 | synthetic pad |

Decode tokens/s in the JSON is an approximate stream-side estimate and
should not be used for engine promotion decisions until the harness
records authoritative `usage.completion_tokens` from a non-stream pass.
TTFT and end-to-end latency are the trusted Phase 1 signals.

## Contract checks

Live localhost checks against `:8082` passed for:

- JSON object response contract;
- tool-call generation (`get_time`) with `tool_choice=auto`.

## Comparison status

| Engine | Status |
|---|---|
| llama.cpp | baseline captured |
| SGLang | experimental Compose scaffold only (`compose.sglang.experimental.yaml`); not installed; no results |
| vLLM | postponed |
| TensorRT-LLM | postponed |

## Decision impact

Per ADR-002, no primary-engine change is justified until an experimental
provider produces a comparable result set with >= 20% material improvement
in the primary interactive metric and no contract regressions.
