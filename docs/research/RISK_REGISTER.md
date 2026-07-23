# Risk Register

Date: 2026-07-23
Scope: risks verified or identified during the Phase 0 audit. Severity is
impact x likelihood on this single-workstation deployment. Owners are
phases from the [implementation plan](IMPLEMENTATION_PLAN.md).

| ID | Risk | Category | Severity | Evidence | Mitigation | Owner |
|---|---|---|---|---|---|---|
| R1 | Host gateways (8888, 8890) listen on `0.0.0.0`; reachable beyond loopback depending on WSL networking mode | security | high | `ss -lntp` at audit time | bind both to `127.0.0.1` via systemd unit env; add a listener check to `verify.sh` | Phase 1 |
| R2 | 3 of 7 deployed model sets are outside the manifest; disaster recovery cannot re-provision reasoning/vision models; 46 GiB orphan set consumes storage | reproducibility | high | manifest vs `/srv/ai-station/models` listing | add manifest entries with immutable revisions + SHA-256, or move orphans to `/srv/ai-station/quarantine` via documented procedure | Phase 1 |
| R3 | GPU at 98% VRAM (23,956 / 24,463 MiB) with the default profile; any extra GPU allocation fails unpredictably | reliability | high | `nvidia-smi` at audit time | admission controller with KV-budget model; consider CPU embedder; document per-profile VRAM envelopes | Phase 1 |
| R4 | No admission check before model switch: gateway starts profiles blind; a mis-sized model file or raised context OOMs the GPU | reliability | medium | gateway code review (`start_runtime`) | dry-run admission decision before `compose up`; typed decisions (START, REJECT, etc.) | Phase 1 |
| R5 | Engine-specific lifecycle logic hardcoded in the gateway blocks any multi-engine future and makes gateway bugs runtime-critical | maintainability | medium | `apps/gateway/app/main.py` review | provider registry + adapter interface; gateway consumes registry instead of constants | Phase 1 |
| R6 | No benchmark or quality evidence for any engine/model decision; 8K context cap unjustified | evidence | medium | absence of `benchmarks/` and of any results | benchmark harness with machine-readable results before any engine change | Phase 1 |
| R7 | WSL2 dxgkrnl does not expose FP8/NVFP4 paths (community-verified for FP8); adopting an engine for FP8/FP4 gains would deliver regressions instead | performance | medium | WSL issue #14452, vLLM issue #37242 | restrict experimental engines to AWQ/GPTQ/GGUF quantizations until local benchmarks prove otherwise | Phase 2/3 |
| R8 | SearXNG and UI-gateway URL fetching create SSRF surface from prompt-controlled content | security | medium | `fetch_url_bytes` accepts arbitrary URLs; SearXNG queries upstream engines | see [threat model](../security/THREAT_MODEL.md) T5; restrict UI-gateway fetches to the Open WebUI origin | Phase 1 |
| R9 | Tool calling disabled platform-wide; agent workloads silently degrade to plain text | capability | medium | `supports_tools: false` across catalog | enable + contract-test tool calling on llama.cpp before any engine comparison | Phase 1 |
| R10 | Whisper cache and Open WebUI state live in one Docker volume; volume loss loses both; backup script scope not verified against it | recoverability | medium | volume layout inspection | include volume in backup procedure; document restore test | Phase 1 |
| R11 | Dead configs (`infra/prometheus`, `infra/caddy`) and unreferenced `apps/` trees mislead future maintainers | maintainability | low | no Compose references | archive or delete after confirming no external consumer | Phase 1 |
| R12 | Single 1 TiB VHDX holds OS, images, and 139 GiB models; 771 GiB free today but an SGLang/TRT-LLM trial adds 20-60 GiB of artifacts | storage | low | `df`, `docker system df` | admission controller checks free storage; artifact budget per phase | Phase 2+ |
| R13 | Redis and SearXNG lack healthchecks; failures surface only as user-visible errors | observability | low | compose.yml review | add healthchecks; extend `verify.sh` | Phase 1 |
| R14 | LiteLLM `main-stable` digest drifts from upstream fixes; upgrade path untested | maintenance | low | image lock review | scheduled lock refresh procedure already exists (`update-image-lock.sh`); exercise it per release | ongoing |
| R15 | SearXNG is AGPL-3.0; unmodified container use is compliant, but any code-level integration must stay arm's-length | licensing | low | license review | keep SearXNG as an unmodified upstream container; document in THIRD_PARTY_NOTICES | ongoing |
| R16 | WSL kernel/driver upgrades can change GPU behavior (CUDA graphs, MMQ kernels) without any repository change | environment | medium | Blackwell/WSL history of behavior shifts | record WSL+driver versions in `config/hardware-profile.json`; re-run smoke benchmark after host upgrades | Phase 1 |
