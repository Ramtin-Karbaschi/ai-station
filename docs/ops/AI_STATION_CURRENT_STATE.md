# AI Station Current State

Verified: 2026-08-27 (DOCKER_CONTEXT=default; `make verify` and `make audit`
passed with Errors 0 / Warnings 0 after operator groups `docker,aidev`)

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
   Ornith 1.5, Qwen3.8, LongWriter-Zero Q4, and ComfyUI MiniMax Music 3 /
   MiniMax H3 / FLUX.2 are retained: never experimental and never deleted.
6. Published endpoints bind to loopback.
7. Docker Compose is the sole supported container runtime.

## Supported runtime

| Component | Role | Deployment | State |
|---|---|---|---|
| llama.cpp | Heavy inference, embeddings, CPU reranking | Digest-pinned Compose | Production core |
| LiteLLM | Project keys, allowlists, stable OpenAI API | Digest-pinned Compose | Production API |
| Host gateway | Canonical model routing, switching, admission | Loopback systemd service | Production |
| UI gateway | Open WebUI attachment/message adaptation | Loopback systemd service | Production |
| Open WebUI | Human chat, Knowledge notebooks, RAG | Compose | Production UI |
| PostgreSQL + pgvector | Application state and retrieval | Compose | Production |
| Redis | WebUI cache/event support | Compose | Production |
| Tika + Tesseract | Extraction and Persian/English OCR | Pinned local image | Production |
| SearXNG | Local metasearch boundary | Compose | Optional egress |
| Graphify | Repository code knowledge graph | Pinned Python venv | Optional client tool |
| OpenCode WSL | Non-root agentic development client | Pinned WSL binary + generated config | Verified developer client |
| ComfyUI | MiniMax Music 3 / H3 and FLUX.2-dev still images | Isolated Compose overlay, loopback `:8188` | Retained production media; GPU-exclusive; never delete (ADR-015, ADR-018) |
| n8n | Visual workflow automation | Compose profile `n8n`, loopback `:5678` | Optional CPU client; off by default; LiteLLM-only (ADR-021) |

## Model capability matrix

| Profile | Public model | Context | Tools | Intended use |
|---|---|---:|---:|---|
| `coder` | Ornith 1.5 35B-A3B (live when that profile is loaded) | 8192 measured; 262144/131072 not probed on this GPU | Yes | Default OpenCode/build agent |
| `general` | Qwen3.8 27B UD-Q4_K_M **live on `:8082`** (`n_params` 27.3B, `n_ctx` **262144**, Q4 KV, flash-attn). 2026-08-27 ingest: 138801 prompt tokens in 190.4 s, 22401 MiB VRAM. | 262144 | Yes | General chat and tool use |
| `ornith` | Ornith 1.5 35B | 8192 | Yes | Compatibility alias of `coder`; never delete |
| `qwen38` | Qwen3.8 27B + mmproj | 262144 | Yes | Compatibility alias of `general`/`vision`; never delete |
| `longwriter` | LongWriter-Zero 32B Q4 | 8192 | No | Retained long-form / RL writing; never delete |
| `reasoning` | Qwen3.8 27B thinking route | 262144 | Yes | Reasoning with shared Qwen3.8 bytes |
| `vision` | Qwen3.8 27B + mmproj | 4096 | Yes | Multimodal requests |
| default embedder | Qwen3 Embedding 8B Q4_K_M **live on `:8090`** (`n_embd` 4096). Knowledge `document_chunk` rebuilt 67/67 at 4096-d. 0.6B GGUF deleted. | 8192 | n/a | CPU (ADR-022). Exact cosine scan (no ANN index above 2000-d). |
| CPU reranker | Qwen3 Reranker 4B Q6_K **live on `:8091`** (`n_params` 4.41B). SHA-256 matches the manifest. `/v1/rerank` returns HTTP 200 but scores are degenerate (~1e-18–1e-30) and ranking order is wrong on a loopback/API probe. | n/a | n/a | Do not accept RAG quality yet. Convert from official `Qwen/Qwen3-Reranker-4B` or restore 0.6B. |

Ornith 1.5, Qwen3.8, LongWriter-Zero Q4, and ComfyUI (MiniMax Music 3,
MiniMax H3, FLUX.2) are **retained operator models**: never experimental
and never deleted. `ai models remove` refuses them.

OpenCode template default is Ornith 1.5 at 8192. Qwen3.8 general/reasoning
advertise **262144** after the 2026-08-27 Q4 KV probe.
The 2026-08-20 Qwen3.8 Reasoning probe passed runtime health and LiteLLM warm-up but a
longer short chat timed out after 180 seconds; it is therefore not advertised
as an agentic/tool model. A 2026-08-23 16-token completion via LiteLLM
`:4000` returned HTTP 200 in 0.941 s (reasoning preamble, `finish_reason=length`).

On 2026-08-23 a sequential live-ops campaign
(`benchmarks/results/20260823/live-ops-summary.json`) passed identity and
tool probes for every catalog chat profile, CPU embedding (0.049–0.077 s)
and rerank, Open WebUI/Tika/SearXNG/n8n/OpenCode/Graphify, and ComfyUI
`/system_stats`. GPU occupancy stayed serial. `ai health` and `ai verify`
exited 0 with `general` restored.

On 2026-08-23 those retained packs were restored after an incorrect
disk-lighten. SHA-256 matched the manifest. The public API advertises
them again. ComfyUI is production media, not experimental. Recommended
sizes and performance: [MODELS.md](../MODELS.md).

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

That is not a document notebook.

### Open WebUI notebooks

Human RAG uses Open WebUI **Workspace → Knowledge**: one collection per
topic, Tika extraction, hybrid BM25 + embeddings, then the CPU reranker.
Operator guide: [clients/OPENWEBUI.md](../clients/OPENWEBUI.md).

### OpenCode

The WSL config for non-root user `aidev` has one provider, `ai-station`, and
four selectable models. Coder, general, and Ornith are tool-capable; Qwen3.8 Reasoning
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
does not replace pgvector. `ai graphify view` serves the upstream HTML map
on loopback `:4174`.

## Operations and storage

~~~text
Code:       /opt/ai-station
Models:     /srv/ai-station/models
Quarantine: /srv/ai-station/quarantine
Backups:    /srv/ai-station/backups
Runtime:    /srv/ai-station/runtime
~~~

The `ai` CLI is the single day-to-day control plane. Windows Manager invokes
it by direct WSL argument passing. Model add/install/verify and recoverable
quarantine/restore are available through `ai models`. Output directories are
selected with `ai output`. The Graphify map is `ai graphify view` on
`http://127.0.0.1:4174/` (ADR-016).

Live verification on 2026-08-22 started ComfyUI, passed `/system_stats`,
generated a 16 s MiniMax Music 3 clip (INT8 DiT, tiled VAE decode,
~187 s) and a MiniMax H3 text-to-video clip (~488 s, about 18 GiB VRAM
observed) from the ComfyUI UI. ComfyUI is **not** promoted. Generated
media stays under `/srv/ai-station/runtime/comfyui/output/`. Raw smoke
dumps stay under `/srv/ai-station/runtime/comfyui/smoke/`. Git keeps
only slim `health.json` and `*-smoke.json` under
`benchmarks/results/`.

## Verified endpoints

| Service | Endpoint | Audience |
|---|---|---|
| Open WebUI | `http://127.0.0.1:3000` | Human users |
| LiteLLM | `http://127.0.0.1:4000/v1` | Apps and OpenCode |
| LiteLLM Admin | `http://127.0.0.1:4000/ui` | Operator API keys |
| Host gateway | `http://127.0.0.1:8888` | Internal routing only |
| UI gateway | `http://127.0.0.1:8890` | Open WebUI only |
| SearXNG | `http://127.0.0.1:8889` | Open WebUI/search |
| Tika | `http://127.0.0.1:9998` | Open WebUI/documents |
| Embedding | `http://127.0.0.1:8090/v1` | Internal retrieval (CPU, ADR-022) |
| Reranker | `http://127.0.0.1:8091/v1` | Open WebUI hybrid RAG (CPU) |
| ComfyUI | `http://127.0.0.1:8188` | Retained media UI; off until `ai provider start comfyui-media-experimental` |
| n8n | `http://127.0.0.1:5678` | Optional workflow UI; off until `ai n8n start` |
| Graphify map | `http://127.0.0.1:4174/` | Optional HTML map; off until `ai graphify view` |
| OpenCode | `http://127.0.0.1:4096` | Developer client health; off until OpenCode is configured |

Heavy model ports (`:8082`–`:8088`) are internal diagnostics, not client
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

2026-08-23 operational campaign: `scripts/live-ops-smoke.sh` wrote
`benchmarks/results/20260823/live-ops-summary.json` (`overall_pass: true`).
`ai start` prints the always-on vs on-demand service directory.

## Upgrade gap (2026-08-27)

`DOCKER_CONTEXT=default`, `make verify`, and `make audit` passed with
`Errors: 0 / Warnings: 0 / RELEASE AUDIT PASSED` after the operator
process gained groups `docker` and `aidev`. Heavy chat is Qwen3.8 on
`:8082`. OpenCode/company-os LiteLLM keys can call the new public names
(opencode completed `key-ok` via `:4000`).

Still open on this workstation:

- Live `:8090` returns **4096-d** embeddings. Open WebUI
  `document_chunk` is `vector(4096)` (67/67). The 0.6B embedding GGUF was
  deleted after the cosine smoke hit the Station notebook fixture.
  Record: `benchmarks/results/20260827/deleted-qwen3-embedding-0.6b.json`.
- Live `:8091` is the 4B GGUF and SHA-256 matches, but a relevance probe
  ranked "Paris" above loopback-binding text. Treat QuantFactory GGUF as
  **not accepted** until an official `Qwen/Qwen3-Reranker-4B` conversion
  beats the 0.6B baseline. Do not delete 0.6B rerank bytes yet.
- Qwen3.8 general is **262144** with Q4 KV + flash-attn (138801-token
  ingest). Vision stays 4096 until a separate mmproj probe.
- PaddleOCR-VL-1.6 is routed in code (Tika first; Tesseract fallback) but
  has no live `:predict` service yet. Qwen3-ASR-1.7B Q8 + mmproj and
  Comfy-Org Z-Image-Turbo NVFP4 / Qwen-Image-Edit-2511 are SHA-pinned in
  the manifest (`studio-2026` / `all`). LTX-2.5 is Hugging Face gated
  until the operator accepts the Lightricks license. Other studio engines
  (FLUX.2-klein, Qwen Image 2512, InfiniteTalk, LatentSync, SeedVR2,
  ThinkSound, Fish S2 Pro, Qwen3-TTS, Hunyuan3D 2.1, ACE-Step 1.5, H3
  ControlNet Union) are not pinned yet.
- Superseded LLM/VL bytes (Qwen3.6, Qwen3-Coder, DeepSeek-R1 Distill,
  Qwen3-VL-32B + mmproj) are gone from `/srv`. Keep Ornith, Qwen3.8,
  LongWriter, MiniMax Music 3 / H3, and FLUX.2.
- Operator shells must keep `DOCKER_CONTEXT=default` (not `rootless`)
  and groups `aidev,docker`. `projects/*.env` files are immutable (`chattr
  +e`); LiteLLM allowlists were updated in the proxy without rewriting those
  files.

## Known limitations

- The single 24 GiB GPU leaves little headroom for one heavy chat
  profile. The embedder is CPU-only (ADR-022). ComfyUI and llama.cpp
  cannot share the GPU.
- SGLang is not a startable provider. The 2026-07-24 trial OOMed; the
  experimental overlay was removed on 2026-08-22 (ADR-002).
- ComfyUI MiniMax / FLUX.2 packs are retained production media and must
  never be deleted. Music3 INT8 tiled-decode and
  H3 FL2VA text-to-video smokes passed on 2026-08-22
  (`benchmarks/results/20260822/comfyui/`). NVFP4 encoder speed under
  WSL2 is still unproven. Image-to-video and reference-to-video were
  not part of that smoke. Overlay names remain historical
  (`comfyui-media-experimental`).
- n8n is CPU-only and can run beside llama.cpp. A scheduled workflow that
  calls LiteLLM can still GPU-swap the heavy profile. Keep cron jobs off
  unless that is intended. Live `/healthz` on `:5678` passed 2026-08-23
  with `llama-cpp-general` still active.
- Qwen3.8 Reasoning is not approved for agentic OpenCode use. A 2026-08-23
  16-token LiteLLM completion passed; a longer 2026-08-20 chat timed out
  at 180 s. Keep it reasoning-only.
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
