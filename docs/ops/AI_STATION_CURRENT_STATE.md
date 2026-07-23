# AI Station Current State

This document records the verified release baseline. It is not a roadmap.

## Active runtime

- Open WebUI;
- LiteLLM multi-project gateway (`:4000`);
- AI Station host gateway (`:8888`, loopback);
- UI gateway (`:8890`, loopback);
- PostgreSQL;
- pgvector;
- Redis;
- SearXNG;
- Apache Tika;
- Tesseract Persian OCR language pack;
- llama.cpp heavy profiles (one at a time): general, coder, reasoning, vision;
- llama.cpp embedding server;
- local faster-whisper large-v3 cache;
- provider registry (`config/providers.yaml`) and admission dry-run.

## Active default models

| Role | Model |
|---|---|
| General reasoning | Qwen3.6 35B-A3B GGUF |
| Embedding | Qwen3 Embedding 0.6B Q8 |

## Selectable heavy profiles

| Role | Model | Default runtime |
|---|---|---|
| General | Qwen3.6 35B-A3B | Active when profile=`general` |
| Coding | Qwen3 Coder 30B-A3B | On demand via `ai models use coder` |
| Reasoning | DeepSeek-R1 Distill Qwen 32B | On demand via `ai models use reasoning` |
| Vision | Qwen3-VL 32B + mmproj | On demand via `ai models use vision` |
| Reranking | Qwen3 Reranker 0.6B | Optional CPU profile |

The authoritative downloaded model list is:

~~~text
config/model-manifest.json
~~~

The authoritative runtime catalog exposed by the gateway is:

~~~text
config/model-catalog.json
~~~

The authoritative provider lifecycle registry is:

~~~text
config/providers.yaml
~~~

## Document processing

The verified extraction path is:

- Apache Tika;
- Tesseract;
- Persian and English OCR.

Docling remains a Phase 5 trial candidate behind a document router.

## Removed or unsupported default components

- ComfyUI;
- FLUX and WAN generation stacks;
- direct cloud model APIs;
- multi-node inference;
- direct public internet exposure;
- unused Caddy/Prometheus stubs (removed in Phase 1).

## Storage

~~~text
Code:       /opt/ai-station
Models:     /srv/ai-station/models
Quarantine: /srv/ai-station/quarantine
Backups:    /srv/ai-station/backups
Runtime:    /srv/ai-station/runtime
~~~

## Verified endpoints

| Service | Endpoint |
|---|---|
| Open WebUI | `127.0.0.1:3000` |
| LiteLLM | `127.0.0.1:4000` |
| General model | `127.0.0.1:8082` |
| Embedding | `127.0.0.1:8090` |
| Host Gateway | `127.0.0.1:8888` |
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
