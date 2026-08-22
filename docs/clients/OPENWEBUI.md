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

Use profile `general` so chat and embeddings share the GPU. ComfyUI must
be stopped first.

1. Open `http://127.0.0.1:3000`.
2. Go to **Workspace → Knowledge**.
3. Create one collection per topic (one "notebook").
4. Upload PDFs or text. Apache Tika extracts text; Tesseract handles
   Persian and English scans.
5. Start a chat with `Qwen3.6-35B-A3B-UD-Q4_K_M`.
6. Attach that Knowledge collection to the chat (Focused Retrieval).
7. Ask questions. Keep generated briefings in **Notes** and attach a
   Note when you need the full draft in context.

Do not enable Native function calling on the chat model if you want
automatic RAG injection. Station default is `function_calling=default`.

## Retrieval path

~~~text
upload → Tika/OCR → Qwen3 embedding (:8090) → pgvector
query  → hybrid BM25 + vectors → CPU Qwen3 reranker (:8091) → top 3 chunks
~~~

Hybrid search and the CPU reranker start with `ai start`. They do not
replace pgvector (ADR-005). Candidate pool is 20 chunks; at most 3 enter
the prompt.

Limits: 20 files, 150 MiB each, 512-token chunks. Full-context mode is
off so large collections cannot overflow the 8192-token chat window.

## Windows Manager

Option 6 opens Open WebUI. Option 22 is LiteLLM API projects, not
notebooks. Reset a forgotten WebUI password with option 38.
