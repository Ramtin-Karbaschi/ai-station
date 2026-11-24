# OpenCode rules for AI Station

- Use local models only through `http://127.0.0.1:4000/v1`; never use `:8888` or `:8083` as client endpoints.
- The `ai-station` provider default is Ornith 1.5 (`coder`). Qwen3.8 is general/escalation; Qwen3.8 Reasoning is reasoning-only unless a live tool probe passes.
- Advertised Qwen3.8 context is 262144 after the 2026-08-27 GPU probe (Q4 KV, 138801-token ingest). Ornith/coder stay at 8192. Read files selectively and preserve native OpenCode compaction behavior.
- Complete the current request with tools such as read, edit, write, and Bash. An empty response or a completion claim without the required file change is a failure.
- For development work, complete the `inspect → edit → test → report` loop. Stop after one concise final report; do not continue reviewing indefinitely.
- For static-site previews, create `index.html` in the current worktree and use `ai opencode preview start .`. Never run a foreground web server, use `npx http-server`, expose a LAN address, or serve a Desktop, home, parent, or drive-root directory.
- Never print secrets or `.env` contents. Keep at most one heavy GPU model active.
- Avoid emoji, especially outside code blocks.
- When `graphify-out/graph.json` exists, begin architecture questions with a narrow `ai graphify query`; do not inject the complete `GRAPH_REPORT.md` into the prompt.
