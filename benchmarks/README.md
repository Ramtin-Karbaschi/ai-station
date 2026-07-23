# AI Station Inference Benchmark Harness

Public-safe, reproducible benchmarks for local inference providers.

## Layout

~~~text
benchmarks/
  README.md
  datasets/          # synthetic and public-safe prompts only
  configs/           # engine/model run configs
  runners/           # execution scripts
  results/           # machine-readable JSON results
  schemas/           # result schema
~~~

## Rules

- Never commit private prompts or proprietary documents.
- Record hardware profile hash/date with every result.
- Same prompts, sampling, context, concurrency, and warm-up policy
  across engines being compared.
- State quantization deviations explicitly (for example GGUF Q4_K_M vs AWQ).

## Quick start

~~~bash
# Dry structural validation
python3 benchmarks/runners/run_openai_bench.py --help

# Live llama.cpp baseline against the active general server
python3 benchmarks/runners/run_openai_bench.py \
  --config benchmarks/configs/llama-cpp-general.yaml \
  --out benchmarks/results/$(date -u +%Y%m%d)/llama-cpp/general-qwen3.6.json
~~~

## Metrics collected

TTFT, prompt tokens/s, decode tokens/s, end-to-end latency, peak VRAM/RAM
when measurable, failure rate, malformed JSON rate, tool-call validity
when tools are exercised.
