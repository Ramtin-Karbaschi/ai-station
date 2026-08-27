# Open WebUI notebooks and RAG

Open WebUI at `http://127.0.0.1:3000` is the human chat and document UI.
Application API keys are a different product surface. See
[PLATFORM.md](../PLATFORM.md).

## Two different "projects"

| What you mean | Where it lives | What it does |
|---|---|---|
| Notebook / research corpus | Open WebUI **Workspace → Knowledge** | Upload sources, retrieve chunks, chat with citations |
| Application identity | `ai projects create ...` | LiteLLM virtual key + model allowlist at `:4000/v1` |

`ai projects` does not store PDFs and does not run RAG.

Graphify is a code graph, not document retrieval
([GRAPHIFY.md](GRAPHIFY.md)). ComfyUI is music/video, not RAG
([COMFYUI.md](COMFYUI.md)).

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

Do not enable Native function calling on the chat model if you want
automatic RAG injection. Station default is `function_calling=default`.

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
