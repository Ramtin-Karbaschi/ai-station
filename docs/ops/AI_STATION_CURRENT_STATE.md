# AI Station Current State

This document records the verified release baseline. It is not a roadmap.

## Active runtime

- Open WebUI;
- AI Station host gateway;
- UI gateway;
- PostgreSQL;
- pgvector;
- Redis;
- SearXNG;
- Apache Tika;
- Tesseract Persian OCR language pack;
- llama.cpp general model server;
- llama.cpp embedding server;
- local faster-whisper large-v3 cache.

## Active default models

| Role | Model |
|---|---|
| General reasoning | Qwen3.6 35B-A3B GGUF |
| Embedding | Qwen3 Embedding 0.6B Q8 |

## Downloaded optional models

| Role | Model | Default runtime |
|---|---|---|
| Coding | Qwen3 Coder 30B-A3B | Not active |
| Reranking | Qwen3 Reranker 0.6B | Not active |

The authoritative downloaded model list is:

~~~text
config/model-manifest.json
~~~

The authoritative runtime catalog exposed by the gateway is:

~~~text
config/model-catalog.json
~~~

Only enabled chat models in that catalog are selectable. Optional coder and
reranker entries remain disabled until a matching Compose service is verified.

## Document processing

The verified extraction path is:

- Apache Tika;
- Tesseract;
- Persian and English OCR.

Docling and experimental OCR/VLM entries are not part of the verified default
runtime.

## Removed or unsupported default components

- ComfyUI;
- FLUX and WAN generation stacks;
- direct cloud model APIs;
- multi-node inference;
- direct public internet exposure.

Legacy catalog entries must not be interpreted as installed or operational
unless they also appear in the active Compose configuration and pass runtime
verification.

## Storage

~~~text
Code:       /opt/ai-station
Models:     /srv/ai-station/models
Cache:      /srv/ai-station/cache
Backups:    /srv/ai-station/backups
Runtime:    /srv/ai-station/runtime
~~~

## Verified endpoints

| Service | Endpoint |
|---|---|
| Open WebUI | `127.0.0.1:3000` |
| General model | `127.0.0.1:8082` |
| Embedding | `127.0.0.1:8090` |
| Gateway | `127.0.0.1:8888` |
| SearXNG | `127.0.0.1:8889` |
| UI Gateway | `127.0.0.1:8890` |
| Tika | `127.0.0.1:9998` |

## Release acceptance

The committed baseline is accepted only when:

~~~text
Errors:   0
Warnings: 0
RELEASE AUDIT PASSED
~~~
