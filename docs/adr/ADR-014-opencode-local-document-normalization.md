# ADR-014: Normalize OpenCode documents before local inference

- Status: Accepted
- Date: 2026-08-21

## Context

OpenCode persisted an attached PDF as a large base64 data URL and sent it to an
8k text-only model. The first request exceeded the useful context budget, after
which native compaction produced 21 compactions, 20 synthetic continuation
messages, and 17 empty assistant messages. Stopping the client was the only way
to end the session.

## Decision

The managed `local-attachments.js` plugin intercepts PDFs in `chat.message`
before persistence. It decodes the attachment locally, extracts Persian and
English text through the loopback Apache Tika service, replaces the binary part
with explicitly untrusted text, and keeps longer extracted text available via
the session-scoped `attachment_read` tool. Raw PDF bytes are neither persisted
by OpenCode nor sent to LiteLLM or a model.

Document turns selected on an 8k profile are routed to the verified 16k Qwen3
Coder model; normal text turns retain the user's picker selection. Provider-size
overflow disables native synthetic auto-continuation so an attachment failure
stops instead of becoming an unbounded compaction loop.

The live OpenCode acceptance suite attaches a public PDF fixture while Ornith is
selected and verifies facts that exist only in the extracted document.

## Consequences

- PDF handling remains offline and local.
- Document text is clearly separated from user instructions.
- Large or malformed PDFs fail closed without leaking binary payloads to a
  text-only model.
- Tika health is part of the station's existing `ai verify` contract.
