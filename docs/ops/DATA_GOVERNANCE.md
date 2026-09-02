# Data Governance

Date: 2026-09-02
Status: Policy. TTL enforcement is Wave 0 work
([ROADMAP.md](../ROADMAP.md)). Application keys are a different
plane ([PLATFORM.md](../PLATFORM.md)).

## Classification

| Class | Examples | Default handling |
|---|---|---|
| Operator config | `.env`, `secrets/`, compose locks | No TTL; backup with the station |
| Application keys | LiteLLM virtual keys | Revoke; do not expire chat history |
| Conversations | Open WebUI chats in PostgreSQL | TTL, default 90 days once enabled |
| Documents | Knowledge uploads, extracted text, vectors | TTL, default 90 days once enabled |
| Media | ComfyUI outputs under runtime | Operator-selectable output roots (ADR-016); not auto-deleted by this policy |
| Models | `/srv/ai-station/models` | Manifest lifecycle only; never implicit delete |

Prompt and response bodies do not go to metrics or health alerts
(ADR-007, ADR-034).

## Retention

Default TTL is **90 days** for conversations and document chunks
after the operator enables the job. Units may set a longer or
shorter TTL; the product default does not start deleting on upgrade
until enabled.

Wave 0 implementation requirements:

- Off unless configured
- Configurable per station (and later per tenant in Wave 3)
- Deletes chat rows and RAG chunks together enough that retrieval
  cannot cite a document whose chat was purged while leaving
  orphan vectors, or the reverse
- Logs counts deleted, not content

## Access

Human access is SSO after Wave 1 (ADR-030). Until then, local
Open WebUI auth is the current runtime. This policy still applies
to stored rows.

## Pre-launch legal

License and regulatory packs are an owner gate immediately before
sale. They are not implemented in this file and do not block Wave 0
TTL work.
