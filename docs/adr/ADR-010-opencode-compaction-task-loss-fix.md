# ADR-010: OpenCode Compaction Task-Loss Fix

- Status: Superseded by ADR-009 and ADR-013
- Date: 2026-08-19
- Superseded: 2026-08-20

## Supersession

The incident and diagnosis below remain valid historical evidence, but the
custom mitigation is no longer part of the system. The project now runs a
current, pinned OpenCode runtime inside WSL with a 16384-token coder context,
40-step build agent, explicit per-deliverable verification, and native
compaction fields only.

`agents/compaction.md` and
`plugins/disable-compaction-autocontinue.js` were removed because they relied
on unstable internal events and added another state machine around the client.
The live `ai opencode acceptance` contract now detects the outcome that
matters: inspect, edit, and test must actually complete. See the 2026-08-20
amendment in [ADR-009](ADR-009-opencode-local-client.md) and the enforced
Desktop-to-WSL boundary in
[ADR-013](ADR-013-opencode-desktop-wsl-and-preview-verification.md).

## Context

A real OpenCode session (`ses_fe6dae8b2ffe6fjvDBmwyTZFgZ`) confirmed a
compounding lossy-summarization bug in `experimental.session.compacting`.
The user's original request (message 1 of the session) was:

> "Create a folder on the Desktop and implement a simple HTML/CSS project
> about advertising for the company DARAEI360."

The exported session JSON showed the compaction subagent's free-text
`objective` field erode across two auto-compactions:

1. Auto-compaction #1 (after ~6553 input tokens, mostly system prompt +
   tool schemas): `objective` still faithful — build the DARAEI360
   HTML/CSS ad project.
2. A synthetic `Continue if you have next steps...` message triggered a
   single `mkdir DARA360` tool call.
3. Auto-compaction #2 fired immediately after that one tool call. Its
   summary **silently dropped the HTML/CSS deliverable** and rewrote
   `objective` as just "create the DARA360 folder" — because the
   compaction subagent re-derived `objective` from the latest tool
   result instead of the literal original request.
4. The session ended with `next_step: none`, `blocker: none` — a false
   completion. The one-continue-per-session circuit breaker (per
   [ADR-009](ADR-009-opencode-local-client.md)) does not fire a second
   continue, so nothing surfaced this as a failure.

The live Windows Desktop folder (`/mnt/c/Users/RamtiN/Desktop/DARA360/`)
was verified empty — no HTML/CSS files were ever written, confirming the
false completion.

This is a structural risk for any 2+ tool-call request on this
workstation, since tool-call overhead alone consumes roughly 80% of the
8192-token compaction budget (documented in
[docs/clients/OPENCODE.md](../clients/OPENCODE.md) and ADR-009), making
repeated compaction within a single session common rather than rare.

## Options considered

1. Leave as-is. Rejected: the false-completion failure mode is silent and
   confirmed to reach the user; no mitigation exists today.
2. Shorten the compaction prompt further. Rejected alone: the bug is not
   caused by prompt length but by the compaction subagent re-deriving
   `objective` from free-text memory of the latest action; a shorter
   prompt does not anchor it to the original request.
3. Deterministic verbatim carry-forward of the original user request via
   the `experimental.session.compacting` plugin hook, plus mandatory
   per-part verification language in `build.md`/`compaction.md`. Adopted.
   Unlike option 2, this is enforced by code (the plugin fetches and
   injects the literal text), so it cannot erode across repeated
   compactions the way the model-generated summary did.

## Evidence

- OpenCode plugin factory signature:
  `export const MyPlugin = async ({ project, client, $, directory, worktree }) => {...}`.
  `client` is an OpenCode SDK client instance available in the factory's
  closure.
- Hook signature:
  `"experimental.session.compacting"?: (input: { sessionID: string }, output: { context: string[]; prompt?: string }) => Promise<void>`.
  If a plugin sets `output.prompt`, `output.context` is entirely ignored,
  so any original-request text must be interpolated directly into the
  `output.prompt` string.
- SDK call `client.session.messages({ path: { id: sessionID } })` returns
  `{ info: Message, parts: Part[] }[]`; `info.role` is `"user"` or
  `"assistant"`. Synthetic auto-continue messages carry `synthetic: true`
  on their text part. The first message in a session is always the real
  original user request and is never deleted by compaction (compaction
  only appends summary messages).
- Verified locally via `tests/test_opencode_client_contract.py`: the new
  `test_compacting_hook_carries_verbatim_first_user_message`,
  `test_compacting_hook_skips_synthetic_first_message`, and
  `test_compacting_hook_degrades_gracefully_without_client` tests spawn
  Node against the real plugin file with fake SDK clients and confirm the
  verbatim carry-forward, synthetic-message exclusion, and graceful
  degradation behaviors.

## Decision

Adopt option 3.

- `config/clients/opencode/plugins/disable-compaction-autocontinue.js`:
  the plugin factory now accepts `{ client }`. In
  `experimental.session.compacting`, it calls
  `client.session.messages({ path: { id: input.sessionID } })` inside a
  try/catch, finds the first message where `info.role === "user"` and no
  part has `synthetic: true`, and takes that message's first text part.
  On any failure (no client, network error, unexpected shape) it falls
  back to an empty string. `output.prompt` is built as a labeled verbatim
  block (`Original user request; preserve verbatim without summarizing or
  rewriting: ...`) followed by the existing four-field template, plus one new
  rule sentence: `objective` must be copied from that verbatim block (not
  re-derived from the latest tool result), and `next_step` must not be
  `none` unless every distinct part of the verbatim request is done. The
  existing `experimental.compaction.autocontinue` one-continue-per-session
  circuit breaker is unchanged.
- `config/clients/opencode/agents/compaction.md` and
  `config/clients/opencode/agents/build.md` each gained one short Persian
  rule reinforcing the same anchor-to-original-request and
  verify-every-part-with-a-tool discipline, for the (less common) case
  where the model still writes the compaction turn itself.
- `tests/test_opencode_client_contract.py`'s prompt-file char-budget
  constant moved from 4800 to 5000 (measured combined total: 4909) with a
  comment explaining the bump.

## Consequences

- Multi-part requests can no longer silently lose a deliverable across
  compaction, because `objective` is anchored to code-injected verbatim
  text rather than model-generated free text that can drift.
- The compaction-time prompt is slightly larger, bounded by the size of
  the original user message (typically a few sentences).
- A second, independent real session (`ses_fe7556b3bffec36EoNn4EiJvYn`,
  reviewed 2026-08-19) later confirmed the same objective-erosion root
  cause: after a `read` confirmed a requested calculator file was already
  complete, auto-compaction relabeled `objective` as "summarize the
  calculator code" instead of confirming the original task, mirroring the
  latest-action re-derivation bug described above. This occurred before
  today's fix and would not reproduce with the deployed verbatim
  carry-forward mechanism.

## Risks

- **Graceful-degradation guarantee:** if the `client.session.messages`
  SDK call fails for any reason (client undefined, network error,
  unexpected response shape), the hook falls back to today's static
  prompt. Compaction never throws and the session never breaks.
- An extremely long original user message could itself consume
  meaningful tokens at compaction time. Acceptable given compaction only
  fires once per context-overflow event, not per turn.

## Rollback

Revert the changes to
`config/clients/opencode/plugins/disable-compaction-autocontinue.js`,
`config/clients/opencode/agents/compaction.md`, and
`config/clients/opencode/agents/build.md`.

## Acceptance criteria

- New and existing tests in `tests/test_opencode_client_contract.py` pass
  (`python3 -m unittest tests.test_opencode_client_contract -v`).
- `node --check` on the plugin file succeeds.
- Manual follow-up (outside this environment's reach — no CLI into the
  Windows OpenCode desktop app): a human restarts OpenCode desktop, opens
  a fresh session, and re-sends the original DARAEI360 prompt to confirm
  the HTML/CSS files are actually created this time.
