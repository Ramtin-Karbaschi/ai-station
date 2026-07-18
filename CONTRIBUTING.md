# Contributing

Contributions that improve correctness, portability, documentation or
operational safety are welcome.

## Before opening an issue

1. Search existing issues.
2. Run the current release audit.
3. Include the operating system, WSL version, Docker version and GPU details.
4. Remove secrets, tokens and personal data from logs.

Security vulnerabilities must follow `SECURITY.md`.

## Pull requests

A pull request should:

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
