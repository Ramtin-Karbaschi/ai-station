# AI Station install pack

Downloadable helpers for standing up AI Station from GitHub.
These scripts do **not** replace NVIDIA driver / WSL2 / Docker prerequisites.

## Prerequisites (once per machine)

| Platform | Required before install |
|---|---|
| Windows 11 | NVIDIA driver + WSL2 (Ubuntu) + Docker Desktop (WSL integration) |
| Linux | NVIDIA driver + Docker Engine + NVIDIA Container Toolkit |
| macOS | Not supported for the default CUDA profile |

Verify inside Linux/WSL:

~~~bash
nvidia-smi
docker version
docker compose version
~~~

## Option A — Download the install pack from Releases

1. Open the latest release: https://github.com/Ramtin-Karbaschi/ai-station/releases/latest
2. Download `ai-station-install-pack.zip`
3. Extract it and open `install/README.md`
4. Run the Windows or Linux bootstrap script for your OS

## Option B — One-line bootstrap (no zip)

Windows PowerShell:

~~~powershell
irm https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/windows/Install-AIStation.ps1 | iex
~~~

Linux:

~~~bash
curl -fsSL https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/linux/install-ai-station.sh | bash
~~~

## Option C — Clone the full repository (recommended for operators)

~~~bash
git clone https://github.com/Ramtin-Karbaschi/ai-station.git
cd ai-station
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
~~~

## Windows 11 (WSL)

From **PowerShell** (Run as your normal user; the script will ask for WSL sudo):

~~~powershell
# After extracting the install pack:
Set-ExecutionPolicy -Scope Process Bypass
.\windows\Install-AIStation.ps1
~~~

Or one-liner that downloads the pack from the latest release:

~~~powershell
irm https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/windows/Install-AIStation.ps1 | iex
~~~

What the script does:

1. checks `wsl` / Docker visibility hints;
2. clones (or updates) the repo inside WSL;
3. runs `./scripts/install.sh --validate-only` then `sudo ./scripts/install.sh`;
4. copies Desktop launchers from `AI Station/`.

Open UI: http://127.0.0.1:3000

## Linux (Ubuntu-class)

~~~bash
curl -fsSL https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/linux/install-ai-station.sh | bash
~~~

Or from an extracted pack:

~~~bash
bash linux/install-ai-station.sh
~~~

## After install

~~~bash
# inside WSL / Linux
ai status
ai verify
~~~

Windows day-to-day: use Desktop shortcuts **AI Station** / **AI Station Manager**.

Application API:

~~~text
http://127.0.0.1:4000/v1
~~~

## Pack contents

~~~text
install/
  README.md                 # this file
  windows/Install-AIStation.ps1
  linux/install-ai-station.sh
~~~

The full Compose stack, image locks, and model manifest always come from the
Git repository — the pack is a bootstrapper, not a standalone offline image.
