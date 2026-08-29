# Grounded Tool Gateway

The Grounded Tool Gateway exposes bounded, typed research primitives to local
applications. It is not an LLM gateway. All model requests continue to use
LiteLLM at `http://127.0.0.1:4000/v1`.

## Endpoint

- Base URL: `http://127.0.0.1:8892/v1`
- Health: `http://127.0.0.1:8892/healthz`
- OpenAPI: `http://127.0.0.1:8892/openapi.json`

The service provides local SearXNG search, bounded text fetch, Wikidata entity
resolution, and content-addressed asset import. Public fetches reject private,
loopback, link-local, reserved, and credential-bearing destinations and
revalidate every redirect.

Imported assets include source URL, source page, SHA-256, retrieval time,
license state, target, and role in a JSON sidecar beside the content-addressed
file. `GET /v1/capabilities` reports canonical Studio capability status;
clients may automate media routes only when the required status is `verified`.

## Operations

```bash
ai tools start
ai tools status
ai tools capabilities
ai tools smoke
ai tools stop
```

Install or refresh the systemd unit with `sudo scripts/install-systemd.sh`.
The service is loopback-only and writes imported assets under
`/srv/ai-station/data/grounding/assets`.

When root access is unavailable, install the equivalent user unit:

```bash
scripts/install-tool-gateway-user.sh
```

The `ai tools` commands discover the system unit first and otherwise manage the
user unit. Do not run both units at once.

No paid API credential is needed. Search uses the local SearXNG service and
entity lookup uses the public Wikidata API. Clients must still treat an empty,
ambiguous, or unavailable result as unresolved rather than inventing an answer.

## Cache and recovery

Back up `/srv/ai-station/data/grounding/assets` together with its JSON sidecars.
Retain content-addressed files referenced by saved projects; remove nothing from
that tree through generic Docker cleanup. Offline mode may reuse only previously
verified cached references and must abstain on uncached entities. To recover,
restore the asset tree with original paths, restart `ai tools`, run
`ai tools smoke`, and verify referenced SHA-256 values before generation.
