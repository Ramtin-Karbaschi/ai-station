# Open WebUI notebooks and RAG

Open WebUI at `http://127.0.0.1:3000` is the human chat and document UI.
Application API keys are a different product surface. See
[PLATFORM.md](../PLATFORM.md). Non-technical steps:
[FAQ.md](FAQ.md).

## Human sign-in with OIDC

OIDC is off by default. The local password form remains available for the
break-glass operator. Before enabling OIDC, create the Admin, Member, and
Viewer groups in Open WebUI and ensure one active local password admin exists.
The setup command refuses to write configuration if it cannot verify those
preconditions.

1. Check the provider metadata with `ai sso probe --issuer <issuer-url>`.
2. Configure using a protected secret file:
   `ai sso configure --issuer <issuer-url> --client-id <client-id> --secret-file <path>`.
3. Recreate Open WebUI with `ai restart`, then review `ai sso status`.

The callback requires at least one configured Admin, Member, or Viewer group
claim; missing and unmapped claims are denied, including on first-user
bootstrap. Admin maps
to Open WebUI `admin`. Member and Viewer map to Open WebUI `user`, and their
separate group memberships remain available for group permissions. Configure
Viewer restrictions on its Open WebUI group; the built-in `user` role alone
does not distinguish Viewer from Member. Group auto-creation and account
merging by email are off.

Successful logins append a content-free record to the private
`/srv/ai-station/runtime/sso/login.jsonl` file. It contains an internal user
identifier, a hashed email, mapped role, outcome, and provider name. It does
not contain tokens, prompts, or chat messages. OAuth callback logs that could
contain token responses, user claims, or exception details are sanitized.
`ai sso disable` turns off OIDC while preserving local operator login.

The checked-in configuration uses synthetic local fixtures only. A customer
issuer and its group mapping still require a separate IdP acceptance drill.

## Voice calls

Open a chat with one model selected and an empty composer. Click the voice
call icon and allow microphone access. Speak in Persian or English. A pause
ends your turn, the station speaks its reply, and the microphone listens for
the next turn. The text conversation remains in the current chat.

Use **End call** or speak a standalone hangup command to release the
microphone. Commands include "end the call" and the Persian equivalents
for ending the conversation or disconnecting the call. Speaking during
playback can interrupt the answer. You can change that behavior with
**Allow Voice Interruption in Call** in Open WebUI settings.

The station transcribes and synthesizes audio locally. Open WebUI reaches
both audio routes through the same LiteLLM connection it uses for chat.
The CPU Piper service selects the voice from the reply text. It has no
published port and requires no second GPU. On a new installation, run
`ai voice setup` to provision the pinned voices and start their service.

Voice Mode uses the dedicated `ai-station-call-asr` transcription model, which
tries CPU faster-whisper first and falls back to Qwen3-ASR if Whisper fails.
Other applications can keep using `ai-station-asr`, whose normal strategy is
Qwen3-ASR first. The standard installation disables Open WebUI persistent
configuration, so recreating Open WebUI after rollout applies the
`AUDIO_STT_MODEL` environment default. If an operator has explicitly enabled
persistent configuration, its saved `audio.stt.model` value takes precedence;
in that case, update only that audio STT setting to `ai-station-call-asr` in
Open WebUI. No global configuration reset is needed.

## Two different "projects"

| What you mean | Where it lives | What it does |
|---|---|---|
| Notebook / research corpus | Open WebUI **Workspace → Knowledge** | Upload sources, retrieve chunks, chat with citations |
| Application identity | `ai projects create ...` | LiteLLM virtual key + model allowlist at `:4000/v1` |

`ai projects` does not store PDFs and does not run RAG.

Graphify is a code graph, not document retrieval
([GRAPHIFY.md](GRAPHIFY.md)). ComfyUI is music/video, not RAG
([COMFYUI.md](COMFYUI.md)).

## Web search and research

**Web Search** is enabled by default in new chats. The **Integrations** menu
shows its current state and lets you change it for that conversation. Check the
menu after reloading a conversation that was already open before a configuration
change.

Models with native tool calling can decide when to query the web, refine a
search, and open individual pages before answering. Ask for primary sources and
linked citations when you need to verify the answer. SearXNG contacts public
search engines, so keep query terms public and omit private document content.

Open WebUI uses the model's own reasoning and tool calls for multi-step research.
For LongWriter, a local Qwen model plans search queries in a separate step.
LongWriter receives relevant excerpts from up to three retrieved pages before
writing. Reasoning controls and result depth vary by model. Vision limits each retrieved page
excerpt to 12,000 characters to leave space for tool calls and the answer.

## Notebook-style workflow

Chat uses the `general` GPU profile (Qwen3.8 27B). Embeddings and the
reranker stay on CPU (ADR-022), so they can run beside that chat
profile. ComfyUI must be stopped first; it cannot share the GPU.

1. Open `http://127.0.0.1:3000`.
2. Go to **Workspace → Knowledge**.
3. Create one collection per topic (one "notebook").
4. Upload PDFs or text. Apache Tika extracts text; Tesseract handles
   Persian and English scans.
5. Start a chat with `Qwen3.8-27B-UD-Q4_K_M`.
6. Attach that Knowledge collection to the chat (Focused Retrieval).
7. Ask questions. Keep generated briefings in **Notes** and attach a
   Note when you need the full draft in context.

The station's `function_calling=default` uses native tools on this Open WebUI
version. Preloaded file context and native knowledge tools are separate model
capabilities.

## Retrieval path

~~~text
upload → Tika/OCR → Qwen3 Embedding 8B (:8090, 4096-d) → pgvector halfvec(4096)
query  → hybrid BM25 + vectors → CPU Qwen3 Reranker 4B (:8091) → top 3 chunks

Do not mix 1024-d or 1536-d rows from retired embedders with 4096-d
vectors. Rebuild every Knowledge collection after an embedding-width
change (`scripts/reindex-openwebui-embeddings.py`). Open WebUI v0.10.2
requires `PGVECTOR_USE_HALFVEC=true` above 2000-d. pgvector cannot
HNSW-index 4096-d halfvec (max 4000), so the reindex script installs a
sentinel HNSW on `subvector(vector,1,4000)` named
`idx_document_chunk_vector`. Retrieval is exact cosine at 67 rows.
~~~

Hybrid search and the CPU reranker start with `ai start`. They do not
replace pgvector (ADR-005). Candidate pool is 20 chunks; at most 3 enter
the prompt.

Limits: 20 files, 150 MiB each, 512-token chunks. Full-context mode is
off so large collections cannot overflow the 262144-token chat window.


## Chat length vs context window

Open WebUI default sampling is `function_calling=default`, `num_ctx` 262144,
and max_tokens 4096 (`DEFAULT_MODEL_PARAMS` in `compose.yml`).

- **262144** is the llama.cpp **context** window for Qwen3.8 general
  (prompt + RAG + history + output). Measured 2026-08-27: Q4 KV,
  flash-attn, 138801-token ingest, 22401 MiB VRAM.
- **4096** is the default **completion** budget. Replies that stop mid-sentence
  with `finish_reason=length` hit this cap, not the 262144 input window.
- Persistent Open WebUI config is off, so compose env is the source of truth.
- Long chat history plus RAG can still fill 262144 and truncate; that is a
  context limit, not the output cap.

## Windows Manager

Option 6 opens Open WebUI. Option 22 is LiteLLM API projects, not
notebooks. Reset a forgotten WebUI password with option 38.
