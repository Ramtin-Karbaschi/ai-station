# AI Station Product

Date: 2026-09-02
Status: Canonical product intent. Runtime truth lives in
[ARCHITECTURE.md](ARCHITECTURE.md), [PLATFORM.md](PLATFORM.md), and
[ops/AI_STATION_CURRENT_STATE.md](ops/AI_STATION_CURRENT_STATE.md).
Build sequence lives in [ROADMAP.md](ROADMAP.md).

## Outcome

AI Station is an on-premises generative-AI workstation sold as a
complete local product: chat, coding agents, document RAG, Persian and
English OCR, private web search, speech, media studio, and workflow
automation. Customer data stays on the customer host. The public
application API is LiteLLM at `http://127.0.0.1:4000/v1`.

The development goal is a shippable product, not an internal lab
stack. Calendar dates are not used; waves in [ROADMAP.md](ROADMAP.md)
run in order as soon as the previous wave meets its acceptance
criteria.

## Buyers and users

| Role | How they use the product |
|---|---|
| Buyer / IT owner | Purchases a loopback-bound station for a sensitive org |
| Operator | Installs, starts profiles, backs up, and verifies with `ai` |
| End user | Signs in with org SSO and uses Open WebUI, media, and notebooks |
| Application | Calls LiteLLM with a project virtual key and a model allowlist |

## Hardware SKUs

Default install assumes **one NVIDIA GPU**. The product must also
run on hosts that have more GPUs or an NPU.

| SKU | Behavior |
|---|---|
| One GPU (default) | One heavy profile at a time (ADR-004 default) |
| Two or more GPUs | Concurrent: one heavy profile per GPU. Tensor-parallel is opt-in configuration, not the default (ADR-031) |
| NPU present | Optional offload of embedding, rerank, and ASR after a local benchmark. Heavy LLM stays on GPU. Absent NPU keeps the CPU path (ADR-032) |

This workstation's snapshot includes an Intel Core Ultra 9 275HX
(Intel AI Boost NPU) and one RTX 5090 Laptop GPU. The live
[`config/hardware-profile.json`](../config/hardware-profile.json)
does not yet record the NPU or a GPU array.

## Identity

Human users authenticate with **SSO / OIDC only** (ADR-030). LDAP is
out of scope. A local break-glass operator account exists only for
bootstrap and recovery. Application isolation stays on LiteLLM
virtual keys and model allowlists, which are machine credentials, not
people.

## Rate limits and monitoring

LiteLLM virtual keys have no default TPM/RPM (ADR-029). Throughput
must not be reduced by a proxy token bucket. Abuse and runaway
clients are detected with **soft alerts**, not blocks (ADR-033).

Observability stays local and small. The next increment is alerts
from signals the station already has (healthchecks, disk, OOM,
container exits, LiteLLM spend tables). Prometheus + Grafana + Loki
are not the next step (ADR-034, ADR-007).

## In scope

- Local inference, RAG, OCR, ASR, ComfyUI media, optional n8n
- Loopback binds and digest-pinned images
- SSO for human users
- Multi-GPU capability with a one-GPU default
- Optional NPU offload for CPU-class work
- Disaster recovery targets and restore drills
- Configurable retention for chats and documents
- Soft usage and health alerts
- Later product surfaces listed in Wave 3 of [ROADMAP.md](ROADMAP.md)

## Out of scope (engineering)

- Cloud-hosted models as the production path
- LDAP / local customer user directories
- Default TPM/RPM caps
- Installing a metrics stack whose storage footprint is unproven
- License and regulatory packs as a development workstream

Legal and license clearance is an owner-held **pre-launch gate**.
It does not block Waves 0-3. Do not wait on it during implementation.

## Non-goals for this document

This file does not replace ADRs, the model catalog, or the verified
runtime snapshot. Link here from [README.md](README.md) when a reader
asks what the product is for.
