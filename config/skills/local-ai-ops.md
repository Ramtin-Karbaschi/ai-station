---
name: local-ai-ops
description: Operational playbook for AI Station, WSL2, Docker, PostgreSQL, Open WebUI, SearXNG, and Tika OCR.
---

# Local AI Ops Skill

## Health checks
- `make status`
- `systemctl status ai-station-gateway ai-station-ui-gateway`
- `curl http://127.0.0.1:8888/health`
- `curl http://127.0.0.1:8890/health`
- `curl http://127.0.0.1:3000`
- `curl "http://127.0.0.1:8889/search?q=test&format=json"`
- `curl -I http://127.0.0.1:9998/tika`
- `df -h /`

## Safety
- Create backups before editing Compose, DB, registry, or launchers.
- Keep model files under `/srv/ai-station/models`.
- Keep project code under `/opt/ai-station`.
- Avoid storing data under `/mnt/c` for WSL workloads.

## Model discipline
- Only one heavy LLM should be loaded at a time on 24GB VRAM.
- The verified default runtime exposes `general-qwen3.6` through the UI gateway.
- Optional coder/reranker weights may exist on disk without being Compose-active.
- Keep experimental models out of the production stack.

## OCR and documents
- Use Apache Tika with the Persian (`fas`) and English Tesseract packs.
- Preserve `/srv/ai-station/models/ocr` for future dedicated OCR runtimes.
- Docling is not part of the verified default runtime.
