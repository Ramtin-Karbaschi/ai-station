# Security Policy

## Supported version

Security fixes currently target the latest commit on the `main` branch.

No earlier release line is guaranteed to receive security updates.

## Reporting a vulnerability

Do not disclose a suspected vulnerability through a public issue, discussion
or pull request.

Use GitHub private vulnerability reporting:

https://github.com/Ramtin-Karbaschi/ai-station/security/advisories/new

Include:

- the affected commit;
- affected component;
- reproduction steps;
- expected and observed behavior;
- security impact;
- suggested mitigation, when available.

## Response targets

The maintainer aims to:

- acknowledge a report within five business days;
- validate severity and scope;
- coordinate a fix before public disclosure;
- credit the reporter when requested and appropriate.

These are operational targets, not contractual guarantees.

## Security scope

Relevant reports include:

- secret disclosure;
- authentication bypass;
- unsafe network exposure;
- command execution;
- path traversal;
- malicious file processing;
- container escape or privilege escalation;
- poisoned model or image provenance;
- dependency or supply-chain compromise.

## Deployment responsibility

The default configuration is designed for a trusted local workstation and
loopback access.

Operators are responsible for additional controls when exposing AI Station to
other devices, including authentication, TLS, firewalling, reverse proxy
hardening and access monitoring.
