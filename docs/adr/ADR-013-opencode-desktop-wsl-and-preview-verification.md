# ADR-013: OpenCode Desktop uses the canonical WSL server

- Status: accepted
- Date: 2026-08-21

## Context

An exported OpenCode session showed that the Windows Desktop had started its
own native server in `C:\Users\...\Desktop`. That server used a stale runtime,
the Ornith profile instead of the default Coder profile, and obsolete custom
compaction assets. The agent changed no files, an auto-compaction summary
claimed that a site had been created, and a foreground `npx http-server`
command exposed a Desktop directory on LAN interfaces before the shell timeout
terminated it. No normal final response was produced.

The WSL runtime and its acceptance checks could not prevent this because the
native Desktop server was a separate execution path.

## Decision

The Windows Desktop remains the graphical UI, but its default server is the
managed OpenCode 1.18.19 service inside WSL. The service runs as `aidev`, starts
in `/opt/ai-station`, binds only to `127.0.0.1:4096`, and reads the canonical WSL
configuration. Windows localhost forwarding reaches this loopback listener
without exposing it on the LAN.

Static previews use `ai opencode preview`. The helper rejects broad roots and
Desktop directories, requires `index.html`, binds to `127.0.0.1`, detaches from
the invoking shell, records process state, and performs an HTTP check before it
reports success.

The live acceptance suite includes both a multi-file Python change and a
website-build-and-preview scenario. The latter passes only when the artifact
exists, HTTP returns a valid page, developer tools were used, and the final
transcript contains the verified URL. Exported sessions can be checked with
`ai opencode audit-session` for the observed failure patterns.

## Consequences

- Desktop sessions and tools execute in the same Linux environment as the
  repository.
- The stale Windows-native configuration is no longer on the default execution
  path; obsolete compaction overrides are removed during Desktop configuration.
- A preview cannot expose a home or Desktop directory through the supported
  command.
- Completion is a verified artifact and observable behavior, not a model claim.

## Rollback

Disable `ai-station-opencode.service` and clear `defaultServerUrl` from
`%APPDATA%\ai.opencode.desktop\opencode.settings`. This rollback restores the
unsafe split-runtime topology and is not recommended.
