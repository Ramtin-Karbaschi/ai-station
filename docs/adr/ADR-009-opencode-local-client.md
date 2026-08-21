# ADR-009: OpenCode as a First-Class Local LiteLLM Client

- Status: Accepted, amended
- Date: 2026-08-18
- Updated: 2026-08-20

## 2026-08-20 amendment: developer runtime boundary

OpenCode must run inside WSL as the dedicated non-root developer user
`aidev`. The native Windows Desktop operating directly on a WSL UNC worktree
is no longer the verified execution path. The pinned WSL runtime, generated
config, `ai opencode doctor`, and a real edit-and-test acceptance harness are
part of the client contract.

The build agent has LSP, formatter, skills, edit, and Bash access inside its
worktree, 40 iterations, coder context/output of 16384/4096, and no external
directory access. Compaction uses only supported native OpenCode fields. The
custom compaction agent and JavaScript continuation hook adopted during the
initial incident response were removed after they proved unstable.

This amendment replaces conflicting operational details below while preserving
the original investigation as historical evidence.

## Context

OpenCode desktop 1.18 was initially installed only on the Windows host. IDE clients must
reach AI Station through the project-facing OpenAI-compatible API, not
the host gateway or a llama.cpp port. The initial default context was 8192
tokens; coder is now 16384.

If OpenCode's `small_model` or hidden title/compaction agents stay on a
different heavy model than the session, every title or compact call
GPU-swaps the single workstation GPU (ADR-004 / ADR-008). A same-day
OpenCode log (`ses_feb517f45ffejYs3F0uGhZntGo`) showed Ornith selected
for `plan`/`build`, then the loop exited with no tools, after which the
same task on Qwen Coder wrote the file. Title/compaction were still
pinned to coder.

A later live Windows config set `enabled_providers: ["ornith"]`. That
fixed the hidden-agent swap but **hid** Qwen3 Coder, Qwen3.6, and
DeepSeek from the picker. Ornith chat also returned empty `content` and
filled `reasoning_content`, so OpenCode could not run an agentic tool
loop. DeepSeek was `tool_call: false`. The project allowlist was coder +
ornith only.

A friend's Ollama/LAN layout (`192.168.1.21:11434`, GGUF-path model ids,
context 87040, `ornith-rag` on `:30890`) is not copied.

## Options considered

1. Leave OpenCode unconfigured; operators paste a cloud or Zen key.
2. Point OpenCode at host gateway `:8888` or llama.cpp coder `:8083`.
3. Treat OpenCode as a first-class LiteLLM client on `:4000` with a
   dedicated project key, coder-pinned default/`small_model`/agents, and
   short managed prompts.
4. Same as 3, plus a second OpenCode provider `ornith` and
   `ai opencode use ornith|coder` so Ornith sessions pin
   model/`small_model`/all agents and `enabled_providers: ["ornith"]`.
5. One provider `ai-station` with all four coding models
   (`tool_call: true`). Picker is the source of truth. Hidden
   title/summary/compaction agents are disabled. `ai opencode use
   <profile>` warms the GPU and sets `model`/`small_model` without
   hiding other picker models. Gateway copies `reasoning_content` into
   empty `content`.

## Evidence

- Platform contract already requires application clients to use
  `http://127.0.0.1:4000/v1` with per-project virtual keys (see
  `docs/PLATFORM.md`). Direct `:8888` / `:8083` bypasses allowlists.
- OpenCode 1.18 schema uses `provider` + `npm: "@ai-sdk/openai-compatible"`
  + `options.baseURL`, `model` / `small_model`, and
  `enabled_providers`.
- One-heavy-GPU policy (ADR-004): a non-matching `small_model` unloads
  the coding runtime during title generation.
- Live `ai opencode test` on 2026-08-18 (coder already loaded; no GPU
  switch): LiteLLM liveliness OK; `GET /v1/models` with the `opencode`
  project key returned `Qwen3-Coder-30B-A3B-Instruct-Q4`; short
  coder chat returned `pong`; tool-call probe returned `get_time`.
- Same-day OpenCode 1.18.18 log for session
  `ses_feb517f45ffejYs3F0uGhZntGo`: auto-compaction on 8k caused a
  "Session Completed" loop; separately, an Ornith picker selection did
  not use tools because hidden agents remained on coder.
- Live Ornith smoke 2026-08-18: GGUF present at
  `/srv/ai-station/models/ornith/ornith-1.0-35b-q4_k_m.gguf`;
  `ai models use ornith` loaded `llm-ornith` on `:8086` (llama.cpp
  `model loaded`); LiteLLM `GET /v1/models` listed
  `Ornith-1.0-35B-Q4_K_M`; tool-call probe returned `get_time`. Short
  chat completed via `reasoning_content` (empty `content` at 64–128
  tokens). `--jinja` was not added. Engine digest was not bumped.
- Follow-up 2026-08-18: live Windows `enabled_providers: ["ornith"]`
  hid the other three models. Engine fix: `llm-ornith` `--reasoning
  off` / `--reasoning-budget 0`, catalog `default_system_prefix:
  "/no_think"`, and gateway flatten of empty `content` from
  `reasoning_content`. DeepSeek OpenCode `tool_call` enabled; catalog
  `supports_tools` stays false (live LiteLLM chat timed out under
  MODEL_LOCK; no successful tool probe).
- Same-day after recreate of `llm-ornith` with `--reasoning off`:
  `ai opencode test --model ornith` returned short chat `content`
  `pong` (not reasoning-only) and tool-call `get_time`. Windows
  `enabled_providers` is `["ai-station"]` with all four models.
- 2026-08-19: LiteLLM warm-up in `ai start` / `ai models use` sent
  llama.cpp alias `local-ornith` and treated HTTP 400 as "runtime may
  still be loading". LiteLLM only lists catalog public ids such as
  `Ornith-1.0-35B-Q4_K_M`. Warm-up now uses `public_name_for_profile`
  and retries until chat-ready; unknown-model 400 is a config error.
- 2026-08-19: with autocontinue fully disabled, Qwen session compacted
  after the first failed `edit` and stopped. Plugin now allows one
  post-compaction Continue per `sessionID` so that tool can retry
  without restoring the 74-continue loop. `small_model` stays equal to
  the selected `model` (compaction must not GPU-swap Ornith to Coder).
- 2026-08-19: confirmed root cause (live logs, not a hypothesis) for
  "Ornith is silent in OpenCode but our probe always passes." At
  07:47:22 UTC, `ai-station-llm-ornith` logged `got exception: ...
  "Unable to generate parser for this template. ... Jinja Exception:
  System message must be at the beginning."` at the exact moment
  `journalctl -u ai-station-gateway` showed a `POST
  /v1/chat/completions` returning HTTP 200 for the corresponding real
  OpenCode session (`new-session---2026-08-19t07-47-21-623z.json`,
  0 tokens, empty content). Cause:
  `rewrite_messages()` (`apps/gateway/app/main.py:234-244`)
  unconditionally inserted a **new** leading
  `{"role": "system", "content": "/no_think"}` message whenever
  `default_system_prefix` was set, even when `body["messages"]` already
  started with its own system message. Real OpenCode requests always
  send a leading system message (agent prompt + tool definitions); the
  `ai opencode test` probe in `scripts/ai` never did, so after the
  insertion the probe always ended up with exactly one system message
  and passed, while real OpenCode ended up with two and hit the Jinja
  guard. llama.cpp catches that internally and returns HTTP 200 with
  empty content/no tokens instead of surfacing an error, so neither
  OpenCode nor LiteLLM ever saw a failure. This supersedes the earlier
  weaker hypothesis that Ornith was only emitting `reasoning_content`
  with an empty `content`; that flatten fallback is still useful for
  other empty-content cases but was not the cause of this silent
  failure. Fix: `rewrite_messages()` now merges the prefix into the
  existing leading system message (single system message at index 0)
  instead of inserting a second one, handling both string and
  multi-part list `content` shapes; `GATEWAY_VERSION` bumped to
  `0.5.2`. Regression test: `tests/test_gateway_message_rewrite.py`.
  The `ai opencode test` probe payloads now include a leading system
  message so this class of bug is caught going forward. Post-fix
  verification: `ai opencode test --model ornith` returned short chat
  `content` `pong` and tool-call probe `get_time`; `docker logs
  ai-station-llm-ornith` for that window shows no Jinja exception.

## Decision

ADR-008 remains unchanged: Coder is the station default. OpenCode is a
first-class client, but its canonical developer runtime is the pinned WSL
binary running as non-root user `aidev`, not the Windows Desktop process.

- The only client endpoint is LiteLLM at `http://127.0.0.1:4000/v1`.
- The single `ai-station` provider exposes Coder, General, Reasoning, and
  Ornith. Coder, General, and Ornith advertise tools; DeepSeek is explicitly
  reasoning-only.
- Coder uses a 16384-token context and 4096-token output budget. Other model
  limits remain conservative until measured KV-cache evidence supports a
  change.
- The build agent has edit, Bash, LSP, formatter, task, and project-skill
  access inside its worktree. External-directory and web access are denied.
- OpenCode uses native `compaction.auto`, `compaction.prune`, and
  `compaction.reserved` fields only. The experimental continuation hook and
  custom compaction agent are not part of the design.
- `ai opencode configure` renders the keyless template into `aidev`'s config,
  preserves an existing backup, and synchronizes the four-model project
  allowlist without printing the key.
- `ai opencode doctor` is the read-only diagnostic. `ai opencode acceptance`
  is the destructive-to-temporary-workspace proof that the build agent can
  inspect, edit, and test code.

## Consequences

Operators install or repair with `ai opencode install --create-user
--own-project`, render config with `ai opencode configure`, and launch with
`ai opencode run /opt/ai-station`. Windows Manager invokes these WSL-native
commands. The picker shows all four models under **AI Station**, while
day-to-day coding defaults to Coder.

Because real OpenCode requests always send a leading system message,
any future `default_system_prefix` catalog entry must go through
`rewrite_messages()`'s merge path (single leading system message), not
a raw insert. `ai opencode test` now sends a leading system message in
its probe payloads specifically so it exercises the same shape as real
OpenCode traffic and would catch a regression of this bug.

## Risks

- Local 30B-class quantized models remain less capable than frontier hosted
  models; acceptance tests prove the workflow, not universal task quality.
- The 16384-token coder context can still fill during long tool traces.
  Native compaction, pruning, bounded agent steps, and scoped prompts mitigate
  this without relying on internal OpenCode events.
- Confirmed (2026-08-19, fixed): a second leading system message
  injected by `rewrite_messages()` made Ornith's Jinja template raise
  "System message must be at the beginning"; llama.cpp swallowed the
  exception and returned HTTP 200 with empty content/no tokens. Fixed
  by merging the prefix into the existing leading system message
  (`GATEWAY_VERSION` 0.5.2). This, not `reasoning_content`-only
  output, was the actual cause of Ornith going silent under real
  OpenCode traffic.
- Ornith may still emit `reasoning_content` for other prompts; flatten
  plus `--reasoning off` remains a fallback for that separate case. Do
  not raise context to 87k without a KV benchmark (ADR-008).
- DeepSeek is explicitly non-agentic (`tool_call: false` and catalog
  `supports_tools: false`). Its 2026-08-20 warm-up passed but short chat timed
  out at 180 seconds, so it remains a selectable reasoning-only profile.
- The generated WSL `opencode.jsonc` contains the project key on disk.
  Mitigation: mode `0600`, ownership by `aidev`, loopback-only API, and no
  generated config in Git.
- `aidev` is intentionally not in the Docker group. OpenCode develops code;
  privileged station lifecycle remains an operator responsibility.
- Windows Desktop may be used as an optional UI through its supported WSL
  server flow, but direct UNC-worktree operation is not an acceptance target.

## Rollback

~~~bash
ai opencode use coder
ai opencode configure
# restore opencode.jsonc.bak-<timestamp> only when explicitly needed
~~~

## Acceptance criteria

- Template has no API key; the single provider `baseURL` is `:4000/v1`;
  no `:8888`, `:8083`, `:11434`, `:30890`, LAN IP, `.gguf` model id, or
  context 87040.
- Default template: `enabled_providers: ["ai-station"]`;
  `model`/`small_model` default to the coder public name; no separate
  `ornith` provider; Coder, Qwen3.6, and Ornith use `tool_call: true`;
  DeepSeek uses `tool_call: false`.
- `agent.build.model` is not pinned. `title`/`summary` are disabled. Build has
  40 steps and the required developer tools.
- `ai opencode use general|coder|reasoning|ornith` sets
  `model`/`small_model` under `ai-station` and does not lock
  `enabled_providers` to a single model.
- Compaction contains only supported `auto`, `prune`, and `reserved` fields;
  no custom compaction agent or continuation plugin exists.
- LiteLLM warm-up uses catalog public ids (not `local-*` aliases) and
  retries until chat-ready.
- `ai opencode configure` writes `/home/aidev/.config/opencode`, enforces
  private permissions, and ensures the live key allowlist contains all four
  public ids.
- `ai opencode doctor` passes all diagnostics as `aidev`.
- Contract tests pass, and the live acceptance harness records tool use, a
  real file edit, and a passing unit test in its disposable repository.
