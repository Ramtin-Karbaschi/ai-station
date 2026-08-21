# Contributing

Contributions that improve correctness, portability, documentation or
operational safety are welcome.

## Git workflow

Use only these three branches:

| Branch | Purpose |
|---|---|
| `development` | All implementation |
| `stage` | Verified release candidate |
| `main` | Production |

Promote `development` → `stage` → `main` after `make check` (and `ai verify`
when runtime behavior changed). Do not create or use any other branch name.

Do not commit editor folders, workstation agent files (`/AGENTS.md`),
secrets, model binaries, or runtime state. The OpenCode client
template `config/clients/opencode/AGENTS.md` is product configuration and
belongs in Git.

Commit messages are conventional and technical (`feat:`, `fix:`, `docs:`,
`refactor:`, `test:`, `chore:`). Explain why in one or two sentences. Do not
add generator footers or co-author trailers.

## Development loop

1. Read the smallest relevant code and its tests before editing.
2. Keep llama.cpp as the inference core and LiteLLM at
   `http://127.0.0.1:4000/v1` as the only application API.
3. Keep lifecycle, OpenCode, Graphify, and model-management logic in
   `scripts/lib/` instead of growing `scripts/ai`.
4. Run a focused test first, then `make check` for a completed change.
5. Runtime changes also require `ai verify`; release work requires
   `scripts/release-audit.sh`.

## Before opening an issue

1. Search existing issues.
2. Run the current release audit.
3. Include the operating system, WSL version, Docker version and GPU details.
4. Remove secrets, tokens and personal data from logs.

Security vulnerabilities must follow `SECURITY.md`.

## Pull requests

A pull request should:

- target `development`;
- address one coherent change;
- explain the reason for the change;
- preserve repository-relative Compose paths;
- avoid committing model binaries or runtime state;
- update documentation;
- include validation commands and results;
- keep the release audit at zero errors and zero warnings.

Run:

~~~bash
./scripts/docs-audit.sh
./scripts/release-audit.sh
~~~

## Licensing of contributions

By submitting a contribution, you agree that your contribution may be
distributed under the repository MIT License.

Do not submit code, models, documentation or assets that you do not have the
right to contribute.
