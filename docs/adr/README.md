# Architecture Decision Records

This directory is the durable decision log. Git preserves history; do not keep
superseded incident notes here after their mitigation has been absorbed by a
live ADR.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-adaptive-inference-fabric.md) | Reduced adaptive fabric: registry, admission, one heavy GPU (default; ADR-031 extends multi-GPU) | Accepted |
| [002](ADR-002-primary-interactive-engine.md) | Retain llama.cpp; reject SGLang (overlay removed) | Accepted |
| [003](ADR-003-llama-cpp-role.md) | llama.cpp owns GGUF chat, vision, embedding, rerank | Accepted |
| [004](ADR-004-resource-admission-control.md) | Start, reduce context, queue, or fallback before GPU conflict (one-GPU default; ADR-031) | Accepted |
| [005](ADR-005-retrieval-engine.md) | Retain pgvector until a measured gap exists | Accepted |
| [006](ADR-006-document-router.md) | Tika default; PaddleOCR-VL-1.6 for hard pages; Tesseract fallback | Accepted |
| [007](ADR-007-observability-boundary.md) | Engine-native metrics only; no SaaS telemetry (next increment ADR-034) | Accepted |
| [008](ADR-008-optional-ornith-heavy-profile.md) | Ornith remains a retained pack; coder profile now loads Ornith 1.5 (ADR-023) | Accepted |
| [009](ADR-009-opencode-local-client.md) | OpenCode is the local LiteLLM client, WSL-native | Accepted |
| [011](ADR-011-opencode-context-kv-cache-headroom.md) | OpenCode Ornith/coder stay 8192; Qwen3.8 general/reasoning advertise 262144 after 2026-08-27 probe | Accepted |
| [012](ADR-012-graphify-code-knowledge-graph.md) | Graphify is an optional code graph, not a pgvector replacement | Accepted |
| [013](ADR-013-opencode-desktop-wsl-and-preview-verification.md) | Desktop uses the canonical WSL OpenCode server | Accepted |
| [014](ADR-014-opencode-local-document-normalization.md) | Normalize attached documents before local inference | Accepted |
| [015](ADR-015-comfyui-minimax-media-studio.md) | ComfyUI is the retained MiniMax music/video studio (never delete) | Accepted |
| [016](ADR-016-operator-console-and-selectable-outputs.md) | `ai` + Windows Manager stay the console; outputs are selectable; Graphify map is loopback HTML | Accepted |
| [017](ADR-017-ornith-1.5-gguf.md) | Ornith 1.5 Q4_K_M GGUF; production coder default as of ADR-023 | Accepted |
| [018](ADR-018-flux2-dev-comfyui.md) | FLUX.2-dev still images on the retained ComfyUI overlay (never delete) | Accepted |
| [019](ADR-019-optional-qwen38-27b-gguf.md) | Qwen3.8-27B UD-Q4_K_M + mmproj; production general/vision as of ADR-023 | Accepted |
| [020](ADR-020-optional-longwriter-zero-32b-q8.md) | Retained LongWriter-Zero-32B Q4_K_M after Q8_0 live smoke failed | Accepted |
| [021](ADR-021-optional-n8n-automation-client.md) | n8n is an optional CPU workflow client; LiteLLM stays the only API | Accepted |
| [022](ADR-022-cpu-embedder-coexistence.md) | Embedder is CPU-only so RAG coexists with one heavy GPU profile | Accepted |
| [023](ADR-023-qwen38-ornith-production-defaults.md) | Qwen3.8 + Ornith 1.5 replace Qwen3.6/Coder/DeepSeek/VL-32B | Accepted |
| [024](ADR-024-embedding-8b-reranker-quality.md) | Embedding 8B (4096-d) live; official 4B Q6_K reranker accepted | Accepted |
| [025](ADR-025-qwen38-max-context.md) | Probe 262144 then 131072; advertise only the measured window | Accepted |
| [026](ADR-026-superseded-model-deletion.md) | Delete superseded bytes after acceptance, not permanent quarantine | Accepted |
| [027](ADR-027-asr-primary-fallback.md) | Qwen3-ASR-1.7B primary; faster-whisper-large-v3 fallback | Accepted |
| [028](ADR-028-local-ai-studio-capabilities.md) | Capability routing on ComfyUI; one heavy GPU; Hunyuan3D isolated | Accepted |
| [029](ADR-029-no-default-litellm-tpm-rpm.md) | LiteLLM virtual keys have no TPM/RPM unless the operator sets them | Accepted |
| [030](ADR-030-sso-only-identity.md) | Human identity is SSO/OIDC only; LDAP rejected | Accepted |
| [031](ADR-031-multi-gpu-default-one.md) | Multi-GPU capable; default one GPU; concurrent per GPU; TP opt-in | Accepted |
| [032](ADR-032-optional-npu-offload.md) | Optional NPU offload for embed/rerank/ASR after local benchmark | Accepted |
| [033](ADR-033-soft-usage-alerts.md) | Soft usage alerts; ADR-029 unlimited keys stay the default | Accepted |
| [034](ADR-034-lean-observability-increment.md) | Lean local alerts next; no Grafana/Loki stack | Accepted |

ADR-010 (custom OpenCode compaction hook) was superseded by ADR-009 and ADR-013
and removed. The incident remains in Git history.
