# OpenCode rules for AI Station

- Use local models only through `http://127.0.0.1:4000/v1`; never use `:8888` or `:8083` as client endpoints.
- The `ai-station` provider exposes Coder (default), Qwen3.6, DeepSeek, and `Ornith-1.5-35B-Q4_K_M`. Ornith does not replace Coder as the default.
- Coder has a 16384-token context; the other profiles use 8192. Read files selectively and preserve native OpenCode compaction behavior.
- Complete the current request with tools such as read, edit, write, and Bash. An empty response or a completion claim without the required file change is a failure.
- For development work, complete the `inspect → edit → test → report` loop. Stop after one concise final report; do not continue reviewing indefinitely.
- For static-site previews, create `index.html` in the current worktree and use `ai opencode preview start .`. Never run a foreground web server, use `npx http-server`, expose a LAN address, or serve a Desktop, home, parent, or drive-root directory.
- Never print secrets or `.env` contents. Keep at most one heavy GPU model active.
- Avoid emoji, especially outside code blocks.
- When `graphify-out/graph.json` exists, begin architecture questions with a narrow `ai graphify query`; do not inject the complete `GRAPH_REPORT.md` into the prompt.
