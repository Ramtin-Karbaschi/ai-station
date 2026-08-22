---
description: Build or query the local code knowledge graph with Graphify
---
If `ai graphify status` reports no graph, run `ai graphify extract --code-only` first.
For an architecture question, use `ai graphify query "<question>"`.
For the relationship between two symbols, use `ai graphify path "<A>" "<B>"`.
For one concept, use `ai graphify explain "<concept>"`.
Humans can open the local HTML map with `ai graphify view` at http://127.0.0.1:4174/ .
Read `GRAPH_REPORT.md` only for a high-level overview. Do not send the graph to a cloud API.
Return one concise answer and stop.
