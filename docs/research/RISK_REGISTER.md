# Risk Register

Date: 2026-07-23
Updated: 2026-08-20
Scope: current residual risks after the production-readiness work. Severity is
impact × likelihood on this single-workstation deployment.

| ID | Risk | Category | Severity | Status | Mitigation / evidence |
|---|---|---|---|---|---|
| R1 | Host gateways listen beyond approved local interfaces | security | high | **mitigated** | Application listeners use loopback; `verify.sh` permits only loopback plus the exact private `docker0` proxy address for the host gateway and rejects wildcard/LAN binds. |
| R2 | Models missing from manifest / orphans | reproducibility | high | **mitigated** | reasoning/vision/mmproj in manifest; orphan coder quarantined then removed |
| R3 | GPU near capacity with default profile | reliability | high | **accepted** | admission budgets + one-heavy-profile policy; embedder shares VRAM |
| R4 | Blind model switch can OOM | reliability | medium | **mitigated** | `ai provider … --dry-run` admission decisions |
| R5 | Hardcoded engine lifecycle in gateway | maintainability | medium | **mitigated** | `config/providers.yaml` + admission module |
| R6 | No benchmark evidence | evidence | medium | **mitigated** | harness + llama.cpp baseline; SGLang failure JSON |
| R7 | FP8/NVFP4 weak under WSL2 | performance | medium | **accepted** | trial used AWQ; SGLang not promoted |
| R8 | SSRF via URL fetch / SearXNG | security | medium | **mitigated** | UI gateway fetch restricted to Open WebUI origin |
| R9 | Tool calling disabled | capability | medium | **mitigated** | catalog flags + contract tests |
| R10 | Whisper + WebUI volume coupling | recoverability | medium | open | Include the volume in backup drills. |
| R11 | Dead Caddy/Prometheus / unused apps | maintainability | low | **mitigated** | stubs removed; legacy `apps/{api,web,worker,ocr}` removed |
| R12 | Large experimental artifacts fill disk | storage | low | **mitigated** | rejected SGLang weights/image removed after ADR-002 |
| R13 | Redis/SearXNG without healthchecks | observability | low | **mitigated** | healthchecks added |
| R14 | LiteLLM digest drift | maintenance | low | open | Exercise `update-image-lock.sh` per release. |
| R15 | SearXNG AGPL | licensing | low | accepted | unmodified upstream container |
| R16 | WSL/driver upgrades change GPU behavior | environment | medium | open | Re-run `ai verify`, OpenCode smoke tests, and the hardware assessment after host upgrades. |
| R17 | The main `scripts/ai` dispatcher remains a large Bash module | maintainability | medium | open | OpenCode and Graphify were extracted into cohesive modules, reducing the dispatcher from 2355 to 1196 lines. Keep contract tests and continue with provider/project/lifecycle extraction without changing the public CLI. |
| R18 | Same-filesystem model quarantine does not reclaim filesystem capacity | storage | medium | accepted | Quarantine is for recoverability and namespace safety; use an explicitly approved archive on another filesystem when capacity recovery is required. Never delete model data implicitly. |
| R19 | DeepSeek reasoning can exceed interactive smoke-test timeouts and has no verified tool protocol | capability | medium | accepted | Advertise it as chat-only; keep coder/general/Ornith as agentic models and benchmark reasoning separately before changing the capability flag. |
| R20 | Graphify indexes can become stale after source changes | developer tooling | low | open | Refresh with `ai graphify extract --code-only`; treat the graph as derived data, never as the source of truth. |
| R21 | Windows launchers depend on WSL distribution/path assumptions | portability | medium | open | Installer owns distribution discovery; CI parses PowerShell entrypoints and the manager validates inputs before invoking WSL. |
| R22 | A local quantized coding model can complete acceptance tasks but still fail on complex repository work | capability | medium | accepted | Use the edit-and-test acceptance harness as a minimum gate, keep human review and focused tests mandatory, and do not equate one passing fixture with frontier-model quality. |

## Review policy

- Reassess open and accepted risks before a release, after a Windows/WSL/GPU
  upgrade, and whenever the model catalog or runtime engine changes.
- A risk may be marked mitigated only when a repeatable command, test, or ADR
  supplies evidence. Documentation alone is not mitigation.
- Model deletion, production runtime replacement, and public network exposure
  always require explicit operator approval.
