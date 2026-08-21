# AI Station Current State

Verified: 2026-08-21

This file is the concise release snapshot: what is supported now, which
boundaries are authoritative, and which limitations are still real. Design
history belongs in ADRs, experiments in `docs/research/`, and user-facing
changes in `CHANGELOG.md`.

## Non-negotiable boundaries

1. llama.cpp is the primary inference core.
2. LiteLLM at `http://127.0.0.1:4000/v1` is the only application API.
3. OpenCode and application projects never target `:8888` or llama.cpp
   runtime ports directly.
4. At most one heavy GPU profile runs at a time.
5. Models and runtime data live under `/srv/ai-station`, outside Git.
   Add and remove those bytes with `ai models add|install|remove|restore`.
6. Published endpoints bind to loopback.
7. Docker Compose is the sole supported container runtime.

## Supported runtime

| Component | Role | Deployment | State |
|---|---|---|---|
| llama.cpp | Heavy inference, embeddings, optional reranking | Digest-pinned Compose | Production core |
| LiteLLM | Project keys, allowlists, stable OpenAI API | Digest-pinned Compose | Production API |
| Host gateway | Canonical model routing, switching, admission | Loopback systemd service | Production |
| UI gateway | Open WebUI attachment/message adaptation | Loopback systemd service | Production |
| Open WebUI | Human chat, RAG, documents | Compose | Production UI |
| PostgreSQL + pgvector | Application state and retrieval | Compose | Production |
| Redis | WebUI cache/event support | Compose | Production |
| Tika + Tesseract | Extraction and Persian/English OCR | Pinned local image | Production |
| SearXNG | Local metasearch boundary | Compose | Optional egress |
| Graphify | Repository code knowledge graph | Pinned Python venv | Optional client tool |
| OpenCode WSL | Non-root agentic development client | Pinned WSL binary + generated config | Verified developer client |

## Model capability matrix

| Profile | Public model | Context | Tools | Intended use |
|---|---|---:|---:|---|
| `coder` | Qwen3 Coder 30B-A3B | 32768 runtime; 16384 OpenCode cap | Yes | Default OpenCode/build agent |
| `general` | Qwen3.6 35B-A3B | 8192 | Yes | General chat and tool use |
| `ornith` | Ornith 1.0 35B | 8192 | Yes | Optional coding agent |
| `reasoning` | DeepSeek-R1 Distill Qwen 32B | 8192 | No | Non-tool reasoning; high latency |
| `vision` | Qwen3-VL 32B + mmproj | 8192 | No | Multimodal requests |
| default embedder | Qwen3 Embedding 0.6B Q8 | 8192 | n/a | Retrieval embeddings |
| optional reranker | Qwen3 Reranker 0.6B Q8 | n/a | n/a | CPU reranking experiments |

Coder uses symmetric q4_0 KV cache at the shared 32768-token runtime ceiling
and leaves about 2568 MiB free VRAM on this GPU. OpenCode retains its verified
16384-token client limit. Other context limits remain unchanged until
model-specific evidence exists (ADR-011).
The 2026-08-20 DeepSeek probe passed runtime health and LiteLLM warm-up but a
short chat timed out after 180 seconds; it is therefore not advertised as an
agentic/tool model.

Authoritative definitions:

~~~text
config/model-manifest.json     downloadable bytes and checksums
config/model-catalog.json      public runtime models and capabilities
config/providers.yaml          lifecycle and admission metadata
config/gateway/litellm.yaml    public API routing
~~~

## Client state

### Application projects

Projects receive one virtual key and an explicit model allowlist. They call:

~~~text
http://127.0.0.1:4000/v1
~~~

### OpenCode

The WSL config for non-root user `aidev` has one provider, `ai-station`, and
four selectable models. Coder, general, and Ornith are tool-capable; DeepSeek
is reasoning only. The build agent has edit, Bash, LSP, formatter, skill
discovery, 40 iterations, and no external-worktree access. Native compaction
uses supported fields only.

Latest live acceptance (2026-08-21):

- OpenCode 1.18.19 was installed from a SHA-256-verified pinned asset;
- `ai opencode doctor` passed 12/12 checks;
- the pinned Python/Bash language and formatting toolchain passed its security
  audit with zero known npm vulnerabilities;
- the official stable OpenCode VS Code extension was installed;
- the real acceptance repository was inspected and edited across three files;
- the resulting Python unit test suite and LSP diagnostics passed;
- GPU was left on the default coder profile.

### Graphify

`graphifyy==0.9.47` is pinned in `config/clients/graphify/manifest.json`.
Code-only extraction, query, and relationship traversal work without a cloud
key or GPU. Generated graphs live under `/srv/ai-station/runtime/graphify/`
and are linked locally as `graphify-out/`; they are never committed. Graphify
does not replace pgvector.

## Operations and storage

~~~text
Code:       /opt/ai-station
Models:     /srv/ai-station/models
Quarantine: /srv/ai-station/quarantine
Backups:    /srv/ai-station/backups
Runtime:    /srv/ai-station/runtime
~~~

The `ai` CLI is the single day-to-day control plane. Windows Manager invokes
it by direct WSL argument passing. Curated model install/verify and
recoverable quarantine/restore are available through `ai models`.

## Verified endpoints

| Service | Endpoint | Audience |
|---|---|---|
| Open WebUI | `http://127.0.0.1:3000` | Human users |
| LiteLLM | `http://127.0.0.1:4000/v1` | Apps and OpenCode |
| Host gateway | `http://127.0.0.1:8888` | Internal routing only |
| UI gateway | `http://127.0.0.1:8890` | Open WebUI only |
| SearXNG | `http://127.0.0.1:8889` | Open WebUI/search |
| Tika | `http://127.0.0.1:9998` | Open WebUI/documents |
| Embedding | `http://127.0.0.1:8090/v1` | Internal retrieval |

Heavy model ports (`:8082`–`:8086`) are internal diagnostics, not client
contracts.

## Quality evidence

The canonical offline gate is:

~~~bash
make check
~~~

It runs the complete unit/cross-file contract suite, Python compilation,
Compose validation, model and image lock validation, and documentation audit.
The release audit additionally verifies the live runtime. CI repeats the
offline gates and parses every PowerShell entrypoint on Windows.

## Known limitations

- The single 24 GiB GPU leaves little headroom with one heavy model plus the
  embedder; admission control and one-heavy-profile exclusivity are required.
- DeepSeek is not approved for agentic OpenCode use because its short live
  chat timed out after warm-up.
- Native Windows Desktop on a WSL UNC worktree is not the verified developer
  path; launch the WSL client through Windows Manager option 28.
- General public exposure and multi-node operation remain unsupported.

## Release acceptance

A release is accepted only when all offline gates pass and the live audit
ends with:

~~~text
Errors:   0
Warnings: 0
RELEASE AUDIT PASSED
~~~
