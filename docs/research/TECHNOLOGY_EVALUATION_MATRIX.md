# Technology Evaluation Matrix

Date: 2026-07-23
Status: Phase 0 research. No component in this matrix has been installed or
benchmarked locally yet unless marked "running today". Cells that could not
be verified from official sources say "not verified". Local benchmark
columns say "requires benchmark" until the Phase 1 harness produces data.

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
| Docling | PDF layout, reading order, TableFormer tables, formula/chart, OCR engines incl. Tesseract | n/a | Python/CLI; JSON/Markdown out | none built-in | standard pipeline CPU-bound; VLM pipeline needs GPU | medium-high | very active (IBM-backed) | VLM table hallucination reports on dense numeric tables; slower than Tika | requires golden-set benchmark | medium (new container + model downloads) | complements Tika for complex PDFs only | trial behind document router (Phase 5) | **trial** (ADR-006) |
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

Community reports are treated as directional only; nothing is adopted
without a local benchmark under this repository's harness.
