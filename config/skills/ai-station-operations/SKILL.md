---
name: ai-station-operations
description: Operate, diagnose, recover, and safely manage AI Station on Windows/WSL2 or Linux. Use this skill whenever the user mentions AI Station status, start/stop/restart, unhealthy services, GPU/model switching, installing or removing model files, backups, OpenCode configuration, Graphify, Windows Manager, or LiteLLM connectivity—even if they only paste an error. It preserves llama.cpp as the inference core and LiteLLM :4000/v1 as the only client API.
compatibility: Requires the AI Station repository and its `ai` CLI; live operations may require WSL2, Docker, systemd, and NVIDIA.
---

# AI Station Operations

Use the repository's `ai` CLI as the public control plane. Wrapper scripts,
raw Compose commands, systemd, and internal ports are diagnostic details, not
parallel operator interfaces.

## Preserve these boundaries

- Applications and OpenCode call `http://127.0.0.1:4000/v1` only.
- llama.cpp is the primary inference core behind LiteLLM and the host gateway.
- Never point a client at `:8888`, `:8083`, or another model runtime port.
- Keep one heavy GPU profile active at a time.
- Keep model bytes under `/srv/ai-station/models`; never delete them broadly.
- Treat Docker Compose as the sole supported container runtime.
- Never print project keys, `.env` values, or generated OpenCode secrets.

## Choose the smallest safe workflow

### Inspect health without changing state

Run:

~~~bash
ai status
ai health
~~~

Use `ai verify` only when a broader live verification is requested. For a
specific provider, use `ai provider status`, `inspect`, or `doctor` before
starting or stopping anything.

For a strictly read-only request, stop at commands whose implementation is
unconditionally observational. Do **not** run `ai opencode test`, `ai verify`,
`ai opencode configure` without `--dry-run`, `ai models use`, Graphify
extraction, or any lifecycle command: these can warm or switch a profile,
rewrite generated client files, refresh derived data, or restart services.
Never infer permission to mutate merely because the requested target already
appears active. If a live contract probe is useful, describe it as the next
step and state its possible side effect.

### Start, stop, or recover the platform

~~~bash
ai start
ai restart
ai stop
~~~

`ai start` restores the last heavy profile, otherwise general. Do not bypass
the lifecycle lock with ad-hoc Compose commands. If startup fails, capture
`ai status`, then bounded logs such as `ai logs snapshot gateway` before
changing configuration.

### Manage active models

~~~bash
ai models list
ai models active
ai models use coder --dry-run
ai models use coder
ai models stop
~~~

Use admission dry-run when memory fit or profile conflicts are uncertain.

### Manage model files

The manifest is the allowlist:

~~~bash
ai models catalog
ai models add <manifest-id>
ai models add --id ID --repo org/name --filename FILE --role ROLE --revision SHA
ai models install <manifest-id>
ai models verify <manifest-id>
ai models remove <manifest-id>              # dry-run
ai models remove <manifest-id> --confirm    # recoverable quarantine
ai models restore <manifest-id> --confirm
~~~

Do not use `rm` for model management. Refuse to remove an active profile;
stop it first. Required core models need the explicit `--allow-required`
guard and should only be quarantined when the user clearly requests it.

### Configure or test OpenCode

~~~bash
ai opencode configure --dry-run
ai opencode configure
ai opencode doctor
ai opencode run /opt/ai-station
ai opencode acceptance
ai opencode use coder
ai opencode test --model coder
~~~

Configuration writes a private config and timestamped backup for the dedicated
WSL developer user `aidev` and keeps one provider, `ai-station`. Use `doctor`
for read-only diagnosis. `run` launches the real developer client as non-root;
the Windows Manager delegates to this WSL path. `acceptance` creates a
disposable repository and proves tool use, editing, and testing. Coder,
general, and Ornith support tools. DeepSeek reasoning is non-agentic and
high-latency; do not recommend it for build/debug tool loops. `test` may
activate its requested model and is therefore a live, conditionally mutating
probe—not a read-only diagnostic.

### Use Graphify

~~~bash
ai graphify status
ai graphify extract --code-only
ai graphify query "what controls model switching?"
~~~

Prefer code-only extraction for routine use: it needs no cloud key or GPU.
Generated graphs stay outside Git. Graphify maps code; it does not replace
pgvector document retrieval.

## Verify proportionally

- Offline code/config change: `make check`.
- Runtime change: `ai verify`, then the relevant live contract.
- Release candidate: full release audit; do not weaken a gate to pass.
- Windows entrypoint change: parse PowerShell and run offline contracts.

## Report structure

Lead with current state or outcome. Then state:

1. evidence observed;
2. action taken, including whether it changed state;
3. verification result;
4. any remaining limitation or rollback command.

Never describe a dry-run as a completed mutation.
