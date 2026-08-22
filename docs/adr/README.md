# Architecture Decision Records

This directory is the durable decision log. Git preserves history; do not keep
superseded incident notes here after their mitigation has been absorbed by a
live ADR.

| ADR | Decision | Status |
|---|---|---|
| [001](ADR-001-adaptive-inference-fabric.md) | Reduced adaptive fabric: registry, admission, one heavy GPU | Accepted |
| [002](ADR-002-primary-interactive-engine.md) | Retain llama.cpp; do not promote SGLang | Accepted |
| [003](ADR-003-llama-cpp-role.md) | llama.cpp owns GGUF chat, vision, embedding, rerank | Accepted |
| [004](ADR-004-resource-admission-control.md) | Start, reduce context, queue, or fallback before GPU conflict | Accepted |
| [005](ADR-005-retrieval-engine.md) | Retain pgvector until a measured gap exists | Accepted |
| [006](ADR-006-document-router.md) | Tika default; Docling remains deferred | Accepted |
| [007](ADR-007-observability-boundary.md) | Engine-native metrics only; no SaaS telemetry | Accepted |
| [008](ADR-008-optional-ornith-heavy-profile.md) | Ornith is optional; coder stays the default | Accepted |
| [009](ADR-009-opencode-local-client.md) | OpenCode is the local LiteLLM client, WSL-native | Accepted |
| [011](ADR-011-opencode-context-kv-cache-headroom.md) | OpenCode coder context stays at the verified 16384 ceiling | Accepted |
| [012](ADR-012-graphify-code-knowledge-graph.md) | Graphify is an optional code graph, not a pgvector replacement | Accepted |
| [013](ADR-013-opencode-desktop-wsl-and-preview-verification.md) | Desktop uses the canonical WSL OpenCode server | Accepted |
| [014](ADR-014-opencode-local-document-normalization.md) | Normalize attached documents before local inference | Accepted |
| [015](ADR-015-comfyui-minimax-media-studio.md) | ComfyUI is the experimental MiniMax music/video studio | Accepted |
| [016](ADR-016-operator-console-and-selectable-outputs.md) | `ai` + Windows Manager stay the console; outputs are selectable; Graphify map is loopback HTML | Accepted |

ADR-010 (custom OpenCode compaction hook) was superseded by ADR-009 and ADR-013
and removed. The incident remains in Git history.
