# Technology Evaluation Matrix

Date: 2026-07-23
Updated: 2026-07-24, 2026-08-19, 2026-08-22
Status: Phase 0–5 decisions recorded. Production stack marked "running
today". SGLang local trial failed to serve (OOM). Retrieval/document
baselines committed under `benchmarks/results/`. Remaining "requires
benchmark" cells are for components not yet justified to install.
2026-08-22 addendum: ComfyUI v0.33.3 adopted as an **experimental**
media-generation studio for MiniMax Music3 and H3 (ADR-015). It is not
a chat engine and is not promoted. NVFP4 under WSL2 remains unverified.
2026-08-19 addendum: llama.cpp quantized KV cache researched as the one
realistic VRAM lever for the original OpenCode 8K context ceiling (see the new
subsection below); local benchmark evidence and the resulting decision
are recorded in `docs/adr/ADR-011-opencode-context-kv-cache-headroom.md`.
Second 2026-08-19 addendum: Graphify (`graphifyy` 0.9.47) adopted as an
optional code knowledge graph (ADR-012); not a retrieval replacement.
The verified coder client now uses a conservative 16384-token context.

Evidence sources are listed per candidate at the end of this document.

## Summary table (part 1: identity and platform fit)

| Component | Category | Version | Release date | License | Hardware compat | WSL2 support | RTX 5090 / Blackwell (sm_120) status |
|---|---|---|---|---|---|---|---|
| llama.cpp (running today) | inference engine | pinned image b9859 (`4fc4ec554`); upstream b10069 | 2026-07-02 (pinned); 2026-07-20 (upstream) | MIT | CPU + CUDA + others | yes (running here) | works today via official CUDA container; community data: CUDA 12.8+MMQ fastest, CUDA 13.x MMQ segfaults (Mar 2026 report); pinned image CUDA path requires benchmark |
| SGLang | inference engine | v0.5.13 | 2026 (current series) | Apache-2.0 | NVIDIA CUDA (SM80+) | community-verified with WSL2 >= 2.7.0 | official SM120 support merged (PR #24692, release notes); FP8 under WSL2 falls back to slow emulated path; AWQ/GPTQ Marlin INT4 recommended |
| vLLM | inference engine | ~v0.19.x | 2026 (rolling) | Apache-2.0 | NVIDIA CUDA + others | community-verified; CUDA graphs OK on WSL2 >= 2.7.0 | pre-built wheels exclude consumer SM120; source build with `TORCH_CUDA_ARCH_LIST=12.0` required (upstream docs PR #38412) |
| TensorRT-LLM | inference engine | v1.3.0+ (NGC container) | 2026 | Apache-2.0 (wheel); NVIDIA container terms | NVIDIA only | partially verified; NGC container is the supported path | SM120 kernels present in v1.3.0+ NGC releases; NVFP4 verified on sm_120 by third parties on native Linux; NVFP4/FP8 under WSL2 dxgkrnl not verified |
| KTransformers / kt-kernel | heterogeneous MoE engine | v0.6.3.post1 | 2026-06-25 | Apache-2.0 | Intel AMX / AVX-512 / AVX2 CPUs + CUDA SM80-90 wheels | not verified | GPU wheels target SM80-90; SM120 not listed; our CPU has no AVX-512/AMX so only the slow AVX2/llamafile path applies |
| pgvector (running today) | vector retrieval | pg17 image (digest-pinned) | current | PostgreSQL License | any | yes (running here) | n/a (CPU) |
| Qdrant | vector retrieval | current stable | 2026 | Apache-2.0 | any; optional GPU indexing | yes (Docker) | n/a for retrieval CPU path |
| Apache Tika + Tesseract (running today) | document extraction | 3.3.0.0 local build | pinned | Apache-2.0 | any | yes (running here) | n/a |
| Docling | document intelligence | v2.9x series | 2026 (active) | MIT | CPU; CUDA optional for VLM pipeline | yes (Python/container) | standard pipeline CPU-only; VLM pipeline GPU use conflicts with the single-heavy-model budget |
| Marker | document intelligence | current | 2026 (active) | GPL-3.0 (weights restrictions) | CPU/GPU | not verified | not verified |

## Summary table (part 2: capabilities and decision)

| Component | Model support | Quantization | API compat | Metrics | Memory behavior | Maturity | Maintenance | Unresolved issues | Benchmark status | Operational cost | Overlap | Proposed classification | Final decision |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| llama.cpp | GGUF everything incl. MoE, vision (mmproj), embeddings, reranking | GGUF K-quants, IQ, FP16 | OpenAI-compatible | `/metrics` (Prometheus) available; not enabled here | predictable; CPU/GPU offload via `-ngl` | high | very active (daily releases) | CUDA 13 MMQ segfault report on Blackwell (external) | baseline requires benchmark | low (running, pinned, installer integration exists) | none (incumbent) | production default | **retain** (ADR-003) |
| SGLang | HF safetensors families incl. Qwen3; not GGUF-first | AWQ, GPTQ (Marlin), FP8 (slow under WSL2), NVFP4 (not verified under WSL2) | OpenAI-compatible | Prometheus metrics | RadixAttention prefix cache; continuous batching; KV paging | medium-high on consumer Blackwell | very active | WSL2 FP8 exposure; consumer SM120 recency; **24 GiB OOM on Qwen3.6-35B-A3B AWQ MoE hybrid (2026-07-24)** | failed local serve; rejected for promotion | medium (new container, new model artifacts in AWQ/GPTQ format) | overlaps llama.cpp for GPU-resident chat only | experimental (retained; not optional-prod) | **reject promotion** (ADR-002) |
| vLLM | HF safetensors; GGUF experimental | AWQ/GPTQ Marlin, FP8 (slow under WSL2), NVFP4 (not verified) | OpenAI-compatible | Prometheus metrics | PagedAttention; continuous batching | medium on consumer Blackwell | very active | consumer SM120 absent from official wheels: source build with pinned commit required | requires benchmark | high (source build, PyTorch nightly pin, rebuild every upgrade) | duplicates SGLang role | rejected for now; re-evaluate if wheels ship SM120 | **postpone** |
| TensorRT-LLM | curated model list; conversion/engine build per model | FP8, NVFP4, AWQ, INT4 | OpenAI-compatible server | metrics available | engine-plan preallocation; least flexible | medium on sm_120 (v1.3.0+) | active (NVIDIA) | WSL2 NVFP4/FP8 exposure not verified; heavy containers; per-model engine builds | requires benchmark | very high | overlaps SGLang/llama.cpp for one curated model | research-only until Phase 6 | **postpone** (Phase 6) |
| KTransformers | very large MoE (DeepSeek-V3-class) via CPU+GPU expert placement | AMXINT4/8 (needs AMX), RAWINT4/FP8 (needs AVX-512), GGUF via llamafile AVX2 | OpenAI-compatible via SGLang integration | partial | CPU-RAM heavy (hundreds of GiB for frontier MoE) | research-grade | active | our CPU lacks AVX-512/AMX; GPU wheels SM80-90; 47 GiB WSL RAM cannot host frontier MoE experts | not applicable on this hardware | very high | overlaps llama.cpp CPU/GPU offload, which already works here | research-only | **reject** for this hardware (revisit on AMX + 128 GiB RAM) |
| pgvector | dense vectors; halfvec/bit quant; SQL filtering; hybrid via tsvector | n/a | SQL | Postgres stats | in-Postgres HNSW | high | active | filtered-search weaker than specialist engines at large scale | retrieval eval requires benchmark (Phase 4) | zero marginal (already required for app data) | none at current scale | production default | **retain** (ADR-005) |
| Qdrant | dense + sparse + multivector, RRF fusion, payload-index filtering | scalar/product/binary | REST/gRPC | Prometheus metrics | Rust engine, low tail latency | high | very active | operational cost of a second stateful store; data-sync pipeline needed | requires benchmark vs pgvector on local corpus | medium | overlaps pgvector | optional profile candidate; adopt only on Phase 4 evidence | **postpone** (Phase 4 evaluation) |
| Tika + Tesseract | 1000+ formats, fas+eng OCR | n/a | REST | none | JVM 3 GiB cap configured | high | stable | table/layout structure lost | golden-set eval requires benchmark (Phase 5) | zero marginal (running) | none as default | production default | **retain** (ADR-006) |
| Docling | PDF layout, reading order, TableFormer tables, formula/chart, OCR engines incl. Tesseract | n/a | Python/CLI; JSON/Markdown out | none built-in | standard pipeline CPU-bound; VLM pipeline needs GPU | medium-high | very active (IBM-backed) | VLM table hallucination reports on dense numeric tables; slower than Tika | Tika golden baseline passed; Docling not installed | medium (new container + model downloads) | complements Tika for complex PDFs only | deferred behind document router | **defer** (ADR-006) |
| Marker | PDF to Markdown, Surya layout | n/a | Python/CLI | none | GPU-accelerated optional | medium | active | GPL-3.0 licensing constraint for a MIT-licensed project; weights usage terms | requires golden-set benchmark | medium | overlaps Docling | fallback candidate only if Docling fails the golden set | **postpone** |

## Workload-class mapping (which engine for which job)

| Workload | Today | Target after evidence |
|---|---|---|
| Interactive general chat | llama.cpp general profile | benchmark llama.cpp vs SGLang (Phase 3 decision) |
| Interactive coding agent | llama.cpp coder profile | same comparison; tool calling must pass first |
| IDE autocomplete | not served | requires low-TTFT provider; decide after Phase 3 data |
| Long-context analysis | capped at 8K | raise per-model context after KV-budget benchmarks |
| Structured output (JSON schema) | llama.cpp grammars (unverified here) | contract tests in Phase 1; SGLang xgrammar in Phase 2 trial |
| Tool-calling agents | disabled everywhere | enable + contract-test on llama.cpp first |
| Embeddings | llama.cpp embedder (GPU) | retain; evaluate CPU placement to free VRAM |
| Reranking | optional CPU profile | wire into RAG only with Phase 4 retrieval eval |
| Multimodal (vision) | llama.cpp + mmproj | retain (GGUF path is the only verified one) |
| Batch reasoning | not served | postpone |
| Very large MoE experimentation | not possible (hardware) | rejected on this hardware |

## 2026-08-19 addendum: llama.cpp quantized KV cache (context-headroom lever)

Researched as the only realistic lever to shrink per-token KV cache VRAM
cost on this hardware without touching model weights, `-ngl`, or
`--parallel` (Track B of the OpenCode task-loss fix; see
`docs/adr/ADR-004-resource-admission-control.md` for the 507 MiB
headroom baseline this is evaluated against).

| Item | Finding | Source | Version / date | Confidence |
|---|---|---|---|---|
| Flag names | `-ctk/--cache-type-k` and `-ctv/--cache-type-v`, allowed values `f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1`, default `f16` for both | official `tools/server/README.md` (upstream master) | fetched 2026-08-19 | confirmed against upstream docs |
| Pinned image support | **Confirmed directly**: ran `docker run --rm --gpus all ghcr.io/ggml-org/llama.cpp@sha256:13f61752307fc4b96c8607a1bc03f977a2a27a4372d194f2aead83d60b964289 --help` on this host and both flags are present with the same allowed values and default `f16` | this repo's own pinned image (`compose.images.lock.yaml`), OCI label `org.opencontainers.image.version=b9859`, revision `4fc4ec5541b243957ae5099edb67372f8f3b550e`, built 2026-07-02 | verified locally 2026-08-19 | primary source (the actual pinned binary, not a doc) |
| Expected VRAM savings | `q8_0/q8_0`: ~50% smaller KV cache than `f16` (halves both K and V); `q4_0/q4_0`: ~75% smaller, but community-measured KV-buffer savings on real hardware were less extreme than the naive 4x figure once quantization metadata overhead is counted (one corrected community benchmark measured -47% for q8_0 and -72% for q4_0 vs. f16 KV buffer size on a 30B-A3B MoE model) | `tools/server/README.md`; ggml-org/llama.cpp Discussion #20969 ("TurboQuant", corrected 2026-04-01 measurement) | discussion updated 2026-04-01; read 2026-08-19 | community-measured, not from this hardware — treated as directional only per this repo's policy |
| Quality caveat | `q8_0/q8_0` is reported as "practically lossless" for most tasks by multiple independent sources; `q4_0/q4_0` is usable but shows measurable coding-quality loss (one source cites ~92% of f16 quality for q4 on code generation vs. ~98% for q8) and "factual drift" risk on long conversations. No official llama.cpp perplexity table specific to GQA or MoE architectures was found; the K cache (not V) is repeatedly flagged as the more quality-sensitive of the two in community writeups. **Unknown**: no upstream, first-party benchmark exists quantifying quality loss specifically for Qwen3-Coder-30B-A3B (MoE) or the Ornith 35B model used by this station — this repo's own tool-calling smoke test (see benchmark below) is the only first-party evidence for those two models | Medium "Optimize your GPU KV cache for llama.cpp" article (secondary, cites unverifiable footnote numbers); arXiv 2601.14277 (quantization survey, Llama-3.1-8B, not GQA/MoE-specific) | read 2026-08-19 | secondary/directional; kept as "requires benchmark" per policy, hence Task 2 below |
| GPU offload caveat | **Important operational caveat, confirmed via upstream issue tracker**: *asymmetric* K/V type combinations (e.g. K=q8_0, V=q4_0) require the build flag `-DGGML_CUDA_FA_ALL_QUANTS=ON`; without it, flash attention silently falls back to a CPU path and prompt processing throughput can collapse by an order of magnitude (one report: 30.6 tok/s vs. 883 tok/s prompt-eval, i.e. ~29x slower, for the exact same prompt only differing in whether the flag was compiled in). *Symmetric* combinations (K=V, e.g. `q8_0/q8_0` or `q4_0/q4_0`) use the default-compiled flash-attention quantized kernels and do not hit this fallback. Unknown whether the pinned `ghcr.io/ggml-org/llama.cpp:server-cuda` image was built with `GGML_CUDA_FA_ALL_QUANTS=ON`; not tested because the benchmark below only used symmetric types, which sidesteps the question | ggml-org/llama.cpp Issue #20866 ("Asymmetric K/V cache quantization types cannot be offloaded to GPU"), closed 2026-03-24, confirmed again by a third party on 2026-06-11 | read 2026-08-19 | confirmed via upstream issue tracker; mitigated by only testing symmetric types |
| Flash attention | `--flash-attn` (`-fa`) accepts `on\|off\|auto`, default `auto` in the pinned image; quantized KV cache generally requires flash attention to be active to get the VRAM savings and avoid the CPU-fallback caveat above | confirmed via pinned image `--help` | verified locally 2026-08-19 | primary source |
| Throughput cost | Community DGX Spark benchmark (Nemotron 30B-A3B, an MoE model of similar scale to `coder`/`ornith`) found symmetric `q8_0` KV cache has negligible generation-speed cost at short/medium context (+0.7% at ~6K, i.e. within noise) but measurable degradation at very long context (-11.9% at ~24K, -36.8% at ~110K) due to per-token dequantization overhead; prompt-processing throughput was reportedly unaffected by cache type at all context lengths tested | ggml-org/llama.cpp Discussion #20969 (corrected data) | corrected 2026-04-01; read 2026-08-19 | community-measured; directionally consistent with this repo's own 8K/12K/16K measurements below, not a substitute for them |

**Conclusion of research (not yet a decision):** `--cache-type-k q8_0
--cache-type-v q8_0` (symmetric, matching the default-compiled kernels)
is the only lever worth benchmarking on this hardware — it is supported
by the exact pinned image, requires no rebuild, and is reported as
near-lossless. `q4_0/q4_0` is a second, more aggressive candidate but
with a real (if disputed) coding-quality risk. Asymmetric combinations
are excluded from the benchmark because of the confirmed CPU-fallback
risk on an image not verified to have `GGML_CUDA_FA_ALL_QUANTS=ON`.
Whether the VRAM saved is *enough* to safely raise context above 8192
on this specific 24 GiB GPU with these specific ~21-22 GB model files is
an empirical question, answered only by the local benchmark and ADR
below — it is not assumed here.

## Evidence sources

| Candidate | Primary sources consulted (2026-07-23) |
|---|---|
| llama.cpp | official releases (ggml-org/llama.cpp, b10069, 2026-07-20); pinned image OCI labels (commit `4fc4ec554`); external Blackwell CUDA-toolkit benchmark report (zenn.dev, Mar 2026) |
| SGLang | official release notes v0.5.13 (SM120 support PR #24692); microsoft/WSL issue #14452 (CUDA graphs on Blackwell, WSL 2.7.0); community WSL2 quantization findings |
| vLLM | upstream docs PR #38412 (consumer Blackwell source-build guide); vllm-project issue #37242 (WSL2 2.7.0 CUDA graphs, FP8 fallback data) |
| TensorRT-LLM | official installation guide (NGC container path); third-party sm_120 verification repos (blackwell-llm-toolkit, May 2026); failed-build report for pre-1.3 versions |
| KTransformers | official repo and kt-kernel README (kvcache-ai); kt-kernel 0.6.3.post1 on PyPI (2026-06-25); SOSP'25 paper |
| pgvector / Qdrant | 2026 comparison literature with recall-pinned benchmarks; Qdrant official docs (hybrid, sparse, RRF) |
| Docling | official docs (pipelines, model catalog); independent table-extraction comparison (Docling vs Marker) |
| llama.cpp quantized KV cache (2026-08-19) | official `tools/server/README.md` (upstream master, fetched 2026-08-19); pinned image `--help` output run directly on this host; ggml-org/llama.cpp Discussion #20969 ("TurboQuant", corrected 2026-04-01); ggml-org/llama.cpp Issue #20866 (asymmetric K/V CPU-fallback, closed 2026-03-24); arXiv 2601.14277 (quantization quality survey); this repo's own local benchmark under `benchmarks/results/20260819/opencode-context/` |

Community reports are treated as directional only; nothing is adopted
without a local benchmark under this repository's harness.

## 2026-08-19 addendum: Graphify (code knowledge graph)

| Item | Finding | Source | Version / date | Confidence |
|---|---|---|---|---|
| Package | Official PyPI name is `graphifyy` (double-y); CLI is `graphify`. Other `graphify*` PyPI names are unaffiliated. | upstream README; PyPI `graphifyy` | 0.9.47, fetched 2026-08-19 | confirmed |
| License | Apache-2.0 on GitHub | Graphify-Labs/graphify | 2026-08-19 | confirmed |
| Code path | Tree-sitter AST, no LLM, no API key; `--code-only` skips docs/PDFs/images | upstream README | 0.9.47 | confirmed locally on a 1-file fixture |
| Docs path | `--backend openai` honors `OPENAI_BASE_URL` / `OPENAI_MODEL` (LiteLLM-compatible) | upstream README env table | 0.9.47 | documented; station default is `:4000` |
| Overlap | Not a vector store. Does not replace pgvector (ADR-005). | upstream README; ADR-012 | 2026-08-19 | decision |
| Classification | optional_profile (coding assistants) | ADR-012 | 2026-08-19 | decision |

Local fixture smoke 2026-08-19: `graphify extract --code-only` wrote 2 nodes / 1 EXTRACTED edge; `query`/`explain` worked with no GPU. Community LOCOMO numbers are directional only and are **not** used to promote Graphify over pgvector.

## 2026-08-22 addendum: ComfyUI MiniMax media studio

| Item | Finding | Source | Version / date | Confidence |
|---|---|---|---|---|
| UI | Native MiniMax H3 and Music3 nodes; Open WebUI cannot run those workflows | Comfy-Org/ComfyUI v0.30.0+; Open WebUI `image_generation` is still-image only | v0.33.3 pin 2026-08-22 | confirmed from upstream |
| H3 official serve | SGLang example uses `--num-gpus 4`; full BF16 ~124 GB | MiniMax-H3 model card | fetched 2026-08-22 | confirmed |
| 24 GiB pack | Comfy-Org pruned INT8 ConvRot + quantized Qwen3-VL encoder | Comfy-Org/MiniMax-H3; Comfy docs | fetched 2026-08-22 | documented |
| Music3 local smoke | INT8 DiT + tiled VAE decode, 16 s, 30 steps, success in 185.7 s, ~13 GiB VRAM observed | `benchmarks/results/20260822/comfyui/music3-smoke.json` | 2026-08-22 | confirmed; still experimental, not promoted |
| H3 local smoke | FL2VA T2V from ComfyUI UI, success in 488 s, ~18 GiB VRAM observed | `benchmarks/results/20260822/comfyui/browser-smoke.json` | 2026-08-22 | confirmed; still experimental, not promoted |
| NVFP4 | Hardware profile: NVFP4 unverified under WSL2 dxgkrnl | `config/hardware-profile.json`; ADR-015 | 2026-08-22 | fallback INT8 encoder named, not assumed |
| Overlap | Media generation, not chat. Does not replace llama.cpp / LiteLLM | ADR-015 | 2026-08-22 | decision |
| Classification | experimental, off by default | ADR-015 | 2026-08-22 | decision |
