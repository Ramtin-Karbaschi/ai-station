# OpenCode developer environment

OpenCode is the agentic development client for AI Station. The supported
execution boundary is **OpenCode inside WSL**, working on the Linux-native
project path as the non-root user `aidev`. LiteLLM remains the only model API.

ADR: [ADR-009](../adr/ADR-009-opencode-local-client.md).
The verified development contract is in this document under
"Verified development contract". Run `ai opencode parity --live` before
calling the workflow complete.

## Supported topology

~~~text
Windows OpenCode Desktop / WSL terminal
        |
        v
OpenCode 1.18.19 server in WSL, user aidev, 127.0.0.1:4096
        |
        +--> read / edit / bash / LSP / skills in the project worktree
        |
        +--> http://127.0.0.1:4000/v1
                    |
                    v
              LiteLLM -> host gateway -> active llama.cpp
~~~

The Windows Desktop is a UI client only. It is configured to connect to the
managed WSL server at `http://127.0.0.1:4096`; the project, shell, tools,
configuration, sessions, and model access all remain in WSL. Running the
Desktop's native local server against a Windows Desktop directory is unsupported.

Official OpenCode guidance also recommends installing and running OpenCode in
WSL for full terminal and development-tool compatibility.

## Install or repair

Run as the AI Station administrator:

~~~bash
ai opencode install --create-user --own-project --dry-run
ai opencode install --create-user --own-project
ai opencode configure
ai opencode desktop configure
ai opencode doctor
~~~

The installer:

- creates the dedicated non-root account `aidev` when requested;
- downloads the version pinned in
  `config/clients/opencode/runtime.json`;
- verifies the GitHub release SHA-256 before installation;
- installs a root-owned binary under `/usr/local/lib/ai-station/opencode/`;
- exposes `/usr/local/bin/opencode`;
- optionally makes `aidev` the Git-worktree owner;
- adds the WSL default user (Cursor) to group `aidev` and sets
  `core.sharedRepository=group` plus a user ACL on `.git`, so both
  accounts can commit without taking the worktree away from `aidev`.

It does not grant `aidev` Docker-group or root privileges.

## Launch

From Windows Manager select **28 — OpenCode developer**. It opens the Desktop
client on the canonical WSL server. The WSL TUI remains available with:

~~~bash
ai opencode run /opt/ai-station
~~~

The launcher refuses an absent developer runtime and executes OpenCode as
`aidev`, never root. LSP tool support is enabled for the process.

## Prove development capability

A chat or raw function-call probe is insufficient. Run the live acceptance
test:

~~~bash
ai opencode acceptance
ai opencode parity --live
~~~

The test creates disposable repositories under the developer home. It starts
with a failing Python unit test and also submits a sample-site build-and-preview
request. It passes only if OpenCode:

1. invokes developer tools;
2. coordinates changes across implementation, public API, and test files;
3. produces a passing unit test suite;
4. completes Python LSP diagnostics.
5. creates a real `index.html` artifact;
6. starts the managed loopback-only preview and passes an independent HTTP check;
7. reports the verified preview URL in its final response.

On 2026-08-21 this contract passed with the local Qwen3 Coder model.

## Developer contract

The generated WSL config enables:

| Capability | Policy |
|---|---|
| Read, grep, glob, list | allowed |
| Edit and bash in build agent | allowed |
| Python/Bash LSP | pinned Pyright and Bash Language Server |
| Python/Bash formatting and linting | pinned Ruff, shfmt, and ShellCheck |
| Project skills | discoverable from `config/skills` |
| Files outside the worktree | denied |
| Web search/fetch | denied by default |
| Filesystem snapshots | enabled |
| Build iterations | 40 |
| Native compaction | auto + prune + 2048-token reserve |
| PDF attachments | local Tika extraction; raw bytes withheld from models |

The previous custom compaction agent and 8k JavaScript continuation hook were
removed. They depended on unstable internal events and could interfere with the
normal development loop. Configuration now uses only supported native
compaction fields.

The managed attachment plugin uses OpenCode 1.18.19's supported `chat.message`
hook to replace PDF data URLs before persistence. Extracted content is wrapped
as untrusted document data. Document turns use Coder's larger verified context
even when an 8k profile is selected; ordinary text turns continue to use the
selected model. Provider-size overflow is fail-stop and cannot auto-continue.

The build agent must execute:

~~~text
inspect -> edit -> test -> report
~~~

It may not declare a multi-part request complete before every requested part is
verified.

## Models

| Profile | OpenCode capability | Context/output |
|---|---|---:|
| coder | default agentic developer | 8192 / 4096 |
| general | tool-capable general work | 262144 / 2048 |
| ornith | optional tool-capable coding | 8192 / 4096 |
| reasoning | analysis/chat; tool_call true | 262144 / 2048 |

All provider entries use
`http://127.0.0.1:4000/v1`. Ports `:8888`, `:8083`, GGUF paths, and
Ollama URLs are internal implementation details and are never client
configuration.

## Commands

~~~bash
ai opencode doctor
ai opencode parity [--live]
ai opencode run [PROJECT_PATH]
ai opencode acceptance [--timeout SECONDS]
ai opencode preview start [DIRECTORY] [--port PORT]
ai opencode preview status|stop
ai opencode audit-session SESSION.json [--json]
ai opencode desktop configure|status
ai opencode use coder|general|ornith|reasoning
ai opencode test --model coder
~~~

`doctor` is read-only. `acceptance` performs inference and writes only to
disposable test repositories. `preview` rejects broad directories, requires an
`index.html`, binds only to `127.0.0.1`, survives shell-tool timeouts, and checks
HTTP before returning. `audit-session` rejects known false-completion and unsafe
preview patterns in an exported session. `use` and `test` may switch the active
heavy GPU profile.

## Troubleshooting order

1. `ai opencode doctor`
2. `ai status` and `ai health`
3. `opencode models ai-station` as `aidev`
4. the live acceptance test
5. a focused LiteLLM/OpenCode log capture

If doctor passes but acceptance fails, retain the acceptance workspace with
`--keep` and inspect the exact tool transcript. Do not repair the symptom by
pointing OpenCode directly at llama.cpp or by running the agent as root.

## Verified development contract

AI Station guarantees a tested local agentic-development workflow. A feature
is called verified only when a repeatable local check proves it.

~~~bash
ai opencode parity --live
~~~

`ai opencode doctor` is read-only. `ai opencode parity --live` performs real
inference and changes only a disposable repository under the developer home.
Treat a failed parity check as a release blocker. Do not bypass LiteLLM.

Project guidance for the OpenCode client is
`config/clients/opencode/AGENTS.md` plus the skills under `config/skills/`.

Commercial editor products have different UIs, remote agents, and review
services. Do not advertise those as OpenCode features. The local build-agent
contract (read, edit, bash, LSP, tests through LiteLLM) remains the supported
surface.
