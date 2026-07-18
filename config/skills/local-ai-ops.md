---
name: local-ai-ops
description: Operational playbook for AI Station, WSL2, Docker, PostgreSQL, Open WebUI, SearXNG, and OCR.
---

# Local AI Ops Skill

## Health checks
- `docker ps`
- `systemctl status ai-station-gateway`
- `curl http://127.0.0.1:8888/health`
- `curl http://127.0.0.1:3000`
- `curl http://127.0.0.1:8889/search?q=test&format=json`
- `curl http://127.0.0.1:5001/ui`
- `df -h /`

## Safety
- Create backups before editing Compose, DB, registry, or launchers.
- Keep model files under `/srv/ai-station/models`.
- Keep project code under `/opt/ai-station`.
- Avoid storing data under `/mnt/c` for WSL workloads.

## Model discipline
- Only one heavy LLM/VLM should be loaded at a time on 24GB VRAM.
- Use the gateway queue and model registry.
- Keep experimental models out of the production stack.

## OCR
- Use Docling for document ingestion and OCR.
- Preserve `/srv/ai-station/models/ocr` for future dedicated OCR runtimes.
