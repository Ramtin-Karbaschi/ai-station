# Risk Register

Date: 2026-07-23
Updated: 2026-07-24
Scope: risks from the Phase 0 audit and follow-on work. Severity is
impact × likelihood on this single-workstation deployment.

| ID | Risk | Category | Severity | Status | Mitigation / evidence |
|---|---|---|---|---|---|
| R1 | Host gateways listen beyond loopback | security | high | **mitigated** | systemd units + `verify.sh` loopback checks; UI/host on `127.0.0.1` |
| R2 | Models missing from manifest / orphans | reproducibility | high | **mitigated** | reasoning/vision/mmproj in manifest; orphan coder quarantined then removed |
| R3 | GPU near capacity with default profile | reliability | high | **accepted** | admission budgets + one-heavy-profile policy; embedder shares VRAM |
| R4 | Blind model switch can OOM | reliability | medium | **mitigated** | `ai provider … --dry-run` admission decisions |
| R5 | Hardcoded engine lifecycle in gateway | maintainability | medium | **mitigated** | `config/providers.yaml` + admission module |
| R6 | No benchmark evidence | evidence | medium | **mitigated** | harness + llama.cpp baseline; SGLang failure JSON |
| R7 | FP8/NVFP4 weak under WSL2 | performance | medium | **accepted** | trial used AWQ; SGLang not promoted |
| R8 | SSRF via URL fetch / SearXNG | security | medium | **mitigated** | UI gateway fetch restricted to Open WebUI origin |
| R9 | Tool calling disabled | capability | medium | **mitigated** | catalog flags + contract tests |
| R10 | Whisper + WebUI volume coupling | recoverability | medium | open | include volume in backup drills |
| R11 | Dead Caddy/Prometheus / unused apps | maintainability | low | **mitigated** | stubs removed; legacy `apps/{api,web,worker,ocr}` removed |
| R12 | Large experimental artifacts fill disk | storage | low | **mitigated** | rejected SGLang weights/image removed after ADR-002 |
| R13 | Redis/SearXNG without healthchecks | observability | low | **mitigated** | healthchecks added |
| R14 | LiteLLM digest drift | maintenance | low | open | exercise `update-image-lock.sh` per release |
| R15 | SearXNG AGPL | licensing | low | accepted | unmodified upstream container |
| R16 | WSL/driver upgrades change GPU behavior | environment | medium | open | hardware profile + re-smoke after host upgrades |
