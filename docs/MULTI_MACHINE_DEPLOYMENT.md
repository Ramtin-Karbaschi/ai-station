# Multi-machine deployment

How to stand up AI Station on another computer **today**, and what a
true one-click installer would still need.

## Reality check (important)

AI Station is a **local NVIDIA GPU workstation stack** (WSL2 or Linux +
Docker + CUDA). It is intentionally not a SaaS product.

| Goal | Status today |
|---|---|
| Repeatable install on a prepared Windows 11 + WSL2 + NVIDIA host | **Supported** via `scripts/install.sh` |
| Repeatable install on Ubuntu + NVIDIA + Docker | **Best effort** via the same installer |
| Single `.exe` that installs drivers, WSL, Docker, models, and starts UI | **Not built yet** (roadmap below) |
| macOS (Apple Silicon / AMD) with the default GPU profile | **Not supported** — no NVIDIA CUDA path |

A frictionless `.exe` cannot honestly skip host prerequisites: NVIDIA
driver, WSL2, Docker, disk space (~80+ GiB), and a multi-gigabyte first
model download will always exist once.

## Supported path today (recommended)

Prefer the GitHub downloadable bootstrap when you want copy-paste commands:

- Release pack: https://github.com/Ramtin-Karbaschi/ai-station/releases/latest
- Scripts in-repo: [`install/README.md`](../install/README.md)

### Windows 11 (primary)

Do these **once** on the target PC (cannot be skipped by any installer):

1. Install a current NVIDIA Windows driver.
2. Enable WSL2 and an Ubuntu distro.
3. Install Docker Desktop with WSL integration.
4. Confirm inside WSL:

~~~bash
nvidia-smi
docker version
docker compose version
~~~

Then install AI Station:

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
~~~

Open:

~~~text
http://127.0.0.1:3000
~~~

Day-to-day from Windows: use the launchers under `AI Station/`
(`AI Station.cmd`, Manager). From WSL: `ai start`, `ai status`, `ai verify`.

Full detail: [INSTALLATION.md](INSTALLATION.md).

### Linux (Ubuntu-class + NVIDIA)

Same installer after Docker Engine + NVIDIA Container Toolkit are working:

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
~~~

Canonical layout remains:

~~~text
/opt/ai-station     # code + config
/srv/ai-station     # models, caches, backups
~~~

### Cloning config from an existing healthy box

To make a second machine feel “already set up”:

1. On the source machine, keep secrets out of Git (never copy real `.env`
   into the repo).
2. Transfer **only** what you intend:
   - optional: `/srv/ai-station/models` (rsync/USB) to skip re-download;
   - optional: Open WebUI volume backup if you need the same chat history;
   - never commit those artifacts.
3. On the target: run `install.sh`, then place models under
   `/srv/ai-station/models` and run `./scripts/verify-models.sh --profile core`.
4. Generate fresh secrets on the new host (`WEBUI_SECRET_KEY`, Postgres,
   LiteLLM keys) unless you deliberately migrate them.

## What “one command” looks like once prerequisites exist

Windows (PowerShell / WSL):

~~~powershell
wsl -d Ubuntu -- bash -lc "git clone https://github.com/Ramtin-Karbaschi/ai-station.git /tmp/ai-station-src && cd /tmp/ai-station-src && sudo ./scripts/install.sh"
~~~

Linux:

~~~bash
curl -fsSL https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/scripts/install.sh -o /tmp/ai-station-install.sh
# Prefer cloning the full repo (locks + Compose files are required):
git clone https://github.com/Ramtin-Karbaschi/ai-station.git && cd ai-station && sudo ./scripts/install.sh
~~~

There is no supported “curl | bash” of a single script without the repo:
digest locks and Compose overlays must travel with the tree.

## Roadmap toward your ideal installer

### Phase A — Bootstrap wrapper (near-term, high value)

Ship a small Windows bootstrap that:

1. checks NVIDIA / WSL / Docker and opens the exact missing install pages;
2. clones this repo into WSL;
3. runs `install.sh --validate-only` then `install.sh`;
4. writes Desktop shortcuts to the existing `AI Station/*.cmd` launchers.

This is an `.exe` or `.msi` **orchestrator**, not a replacement for WSL/Docker.

### Phase B — Offline pack (optional)

A signed USB/ISO-style pack containing:

- digest-pinned container images (`docker save`);
- Core GGUF models with SHA-256;
- the Git tree at a release tag.

Target machines then install without Hugging Face/Docker Hub on first boot.

### Phase C — Full silent enterprise installer (large project)

Would need: driver detection, WSL provisioning, Docker install, GPU
toolkit, secrets generation, model placement, service registration, and
rollback. That is a separate product effort beyond the current workstation
repo.

## macOS note

Default AI Station profiles assume NVIDIA CUDA containers. Apple Silicon
would need a different engine/quantization matrix and is out of scope
until an ADR + local benchmarks exist. Do not expect the current
`install.sh` path to “just work” on Mac.

## Acceptance checklist on every new machine

~~~text
./scripts/install.sh --validate-only   # 0 errors / 0 warnings
sudo ./scripts/install.sh
./scripts/verify.sh
./scripts/release-audit.sh             # optional but recommended
curl -fsS http://127.0.0.1:3000 >/dev/null
curl -fsS http://127.0.0.1:4000/health/liveliness >/dev/null
~~~

If those pass, the new system is ready for daily use.
