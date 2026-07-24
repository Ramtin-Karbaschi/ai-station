# Inference Benchmark Report

Date: 2026-07-24
Status: Phase 3 decision complete. llama.cpp retained; SGLang promotion rejected on this hardware.

## Scope

Compare production `llama.cpp` general provider
(`ai-station-general`, GGUF Q4_K_M) against experimental SGLang
(`ai-station-sglang-general`, AWQ-4bit Marlin) on the RTX 5090 Laptop
under WSL2.

## llama.cpp baseline (trusted)

Result file:

~~~text
benchmarks/results/20260723/llama-cpp/general-qwen3.6.json
~~~

| Case | OK | TTFT (ms) | E2E (ms) | Notes |
|---|---|---|---|---|
| short-prompt | yes | 4473 | 4723 | |
| code-generation | yes | 4457 | 35054 | |
| json-schema-like | yes | 4321 | 8112 | |
| context-8k-synthetic | yes | 6000 | 6575 | synthetic pad |

Decode tokens/s in that JSON is approximate. TTFT and end-to-end latency
are the trusted Phase 1 signals. Live JSON-object and tool-call contracts
on `:8082` passed.

## SGLang experimental (failed to serve)

Result file:

~~~text
benchmarks/results/20260724/sglang/general-qwen3.6-awq-oom.json
~~~

| Attempt | Config | Outcome |
|---|---|---|
| 1 | awq + bfloat16 | rejected by SGLang (AWQ requires float16) |
| 2 | awq_marlin + float16, ctx 8192 | weights ~22.5 GiB; mamba cache OOM (−4.95 GiB) |
| 3 | awq_marlin + float16, ctx 4096, cpu-offload 6 GiB | cuda/cpu device mismatch |

No TTFT/E2E numbers were collected because `/v1/models` never became healthy.

## Quantization caveat

GGUF Q4_K_M vs AWQ INT4 is not exact parity. That caveat is moot for
promotion: SGLang never reached a runnable state for this MoE hybrid
artifact on 24 GiB.

## Decision impact

Per ADR-002 (Accepted 2026-07-24): retain llama.cpp; reject SGLang
promotion on this workstation for the incumbent model family. vLLM and
TensorRT-LLM remain postponed.
