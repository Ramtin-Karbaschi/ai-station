# ADR-012: Graphify as an Optional Code Knowledge Graph

- Status: Accepted
- Date: 2026-08-19

## Context

AI coding assistants on this workstation (OpenCode) re-read and
grep source on every session. Graphify (`graphifyy` on PyPI, CLI
`graphify`) maps a repository into a local traversable graph
(`graph.json`) with tree-sitter AST for code (no LLM) and an optional
semantic pass for docs/PDFs/images.

pgvector remains the production **document retrieval** store (ADR-005).
Graphify is a **code/architecture graph**, not a vector index. The two
workloads do not overlap.

OpenCode originally had an 8192-token context; the verified Coder profile is
now 16384 (ADR-009 / ADR-011). Upstream's default OpenCode skill is a
~700-line always-on extraction runbook and would still consume an unjustified
share of the local model's prompt budget. The station therefore vendors a
**short** command plus CLI, and does not install the upstream skill verbatim.

## Options considered

1. Do not add Graphify; keep grep/Read as the only code-orientation path.
2. Run upstream `graphify install --platform opencode` and other
   editor-specific installers unmodified (full skill + alwaysApply rule).
3. Pin Graphify in an isolated venv, expose it through `ai graphify`,
   default to `--code-only` (no GPU), optional docs pass via LiteLLM
   `:4000`, short OpenCode instructions, graphs under
   `/srv/ai-station/runtime`.

## Evidence

- Official package `graphifyy==0.9.47` (wheel SHA-256
  `2a8b13ccd53d507d16dcc12aebe488517c369afa547938464474fd3e772938ab`),
  license Apache-2.0, Python >=3.10. Source:
  https://github.com/Graphify-Labs/graphify (fetched 2026-08-19).
- Local smoke (2026-08-19): `graphify extract /tmp/graphify-fixture
  --code-only` produced 2 nodes / 1 edge with no API key; `query` and
  `explain` returned EXTRACTED edges. No GPU involved.
- Code-only extraction needs no API key (upstream README). Docs/PDF
  extraction uses `--backend openai` against
  `OPENAI_BASE_URL=http://127.0.0.1:4000/v1` (LiteLLM), not cloud.
- Community LOCOMO numbers are directional only; no local apples-to-apples
  retrieval benchmark vs pgvector is claimed. Graphify is **not**
  promoted as a document-RAG replacement.

## Decision

Adopt option 3.

- Classification: **optional profile** (coding-assistant skill / CLI).
- Package pin: `config/clients/graphify/manifest.json`.
- Isolated venv: `/opt/ai-station/.venvs/graphify` (gitignored).
- Graphs: `/srv/ai-station/runtime/graphify/<project>/graphify-out/`
  (runtime state, not committed).
- Default extract: `--code-only` (tree-sitter, offline, no GPU).
- Optional `--docs`: LiteLLM loopback, current OpenCode project key,
  `--max-concurrency 1`, `--token-budget 4096` (local coder context).
  `ai graphify install` includes the pinned `openai` and `pdf` extras so
  that backend can talk to `:4000` and parse PDFs. Never cloud Gemini/OpenAI
  as default.
- OpenCode: short `/graphify` command + plugin reminder. Do **not**
  deploy the upstream 700-line skill into the 8k system prompt.
- Uninstall: `ai graphify uninstall` (venv); `--purge` also deletes
  runtime graphs. Does not stop GPU providers.

## Consequences

Operators can build and query a code graph without a GPU. Assistants
can answer architecture questions from `graph.json` instead of grepping.
Semantic (docs) extraction remains opt-in and shares the single heavy
GPU via LiteLLM / admission (ADR-004). `ai graphify view` (ADR-016)
writes upstream HTML and a loopback map; assistants still query
`graph.json`.

## Risks

- Upstream skill/plugin wording can drift on upgrade. Mitigation: pin
  `0.9.47` in the manifest; station-owned short prompts, not the
  upstream skill dump.
- OpenCode 8k overflow if a future configure copies the full skill.
  Mitigation: contract test that the OpenCode command file stays short.
- Graph stale after refactors. Mitigation: `ai graphify extract`
  (or `graphify update`) is explicit; no post-commit hook by default.
- Docs pass can GPU-swap the heavy profile. Mitigation: `--docs` is
  opt-in; default is code-only.

## Rollback

~~~bash
ai graphify uninstall --purge
~~~

Remove `config/clients/opencode/commands/graphify.md` and
`config/clients/opencode/plugins/graphify.js`, then `ai opencode configure`.

## Acceptance criteria

1. `ai graphify install` creates the pinned venv and `graphify --version`
   reports `0.9.47`.
2. `ai graphify extract --code-only` of this repo writes
   `graph.json` under `/srv/ai-station/runtime/graphify/` without
   calling LiteLLM.
3. `ai graphify query` returns nodes for a known symbol (e.g. admission
   or `cmd_opencode`) from that graph.
4. OpenCode `/graphify` command is under 2500 characters.
5. Default docs backend is `http://127.0.0.1:4000/v1`, never a public
   cloud URL.
6. `ai graphify uninstall` removes the venv; `--purge` removes graphs.
7. `ai graphify view --no-serve` writes `graph.html` next to `graph.json`.
