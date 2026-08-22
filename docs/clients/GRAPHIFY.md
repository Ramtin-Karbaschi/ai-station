# Graphify on AI Station

Graphify maps a repository into a local knowledge graph (tree-sitter AST
for code; optional LiteLLM pass for docs). It is an **optional**
coding-assistant tool, not a replacement for pgvector retrieval.

ADR: [ADR-012](../adr/ADR-012-graphify-code-knowledge-graph.md),
[ADR-016](../adr/ADR-016-operator-console-and-selectable-outputs.md)

## Install and use

~~~bash
ai graphify install
ai graphify configure          # OpenCode command/plugin
ai graphify extract --code-only
ai graphify query "what connects LiteLLM to llama.cpp?"
ai graphify path "cmd_opencode" "LiteLLM"
ai graphify explain "admission"
ai graphify status
ai graphify view               # loopback map at http://127.0.0.1:4174/
~~~

`--code-only` is the default: offline, no GPU, no API key.

`--docs` sends document/PDF/image chunks to LiteLLM at
`http://127.0.0.1:4000/v1` with the OpenCode project key
(`--max-concurrency 1`, `--token-budget 4096` for the local coder
context). `ai graphify install` therefore pulls the
pinned `openai` and `pdf` extras (LiteLLM + local PDF parsing), never
Gemini or a public cloud SDK. Do not point Graphify at a public cloud API.

## Graphical map

`ai graphify view` regenerates upstream `graph.html` (force graph,
self-contained) and `GRAPH_TREE.html` (module tree; needs outbound HTTPS
for D3), plus a station map that links those files and the loopback UIs.
It binds `127.0.0.1:4174` only. Stop with `ai graphify view --stop`.
Windows Manager option **42** opens the same map.

Coding assistants should keep using `query` / `path` / `explain` against
`graph.json`. Do not paste the full `GRAPH_REPORT.md` into a prompt.

## Where the graph lives

Runtime state (not git):

~~~text
/srv/ai-station/runtime/graphify/<project>/graphify-out/graph.json
~~~

Change the parent directory:

~~~bash
ai output set graphify /srv/ai-station/runtime/graphify/ai-station
ai graphify extract --code-only --out /srv/ai-station/runtime/graphify/ai-station
~~~

`ai graphify extract` of this repo also symlinks `graphify-out/` in the
workspace. The symlink is gitignored.

## Editor notes

Local editor rules may remind the assistant to run `ai graphify query`
when `graphify-out/graph.json` exists. Those rules stay on the workstation
and are not committed.

## OpenCode

`/graphify` is a short command that calls `ai graphify …`. The upstream
700-line OpenCode skill is **not** installed: the three curated
AI Station skills cover project workflows without flooding model context.
A plugin reminds once per session when
`graphify-out/graph.json` exists.

After `ai graphify configure` (or `ai opencode configure`), start a new
WSL-native OpenCode session.

## Uninstall

~~~bash
ai graphify uninstall           # venv only
ai graphify uninstall --purge   # venv + runtime graphs
ai graphify view --stop
~~~
