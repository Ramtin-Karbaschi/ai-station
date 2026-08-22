#Requires -Version 5.1
<#
.SYNOPSIS
  Bootstrap AI Station on Windows 11 + WSL2.

.NOTES
  Prerequisites: NVIDIA driver, WSL2 Ubuntu, Docker Desktop with WSL GPU.
  Run:
    irm https://raw.githubusercontent.com/Ramtin-Karbaschi/ai-station/main/install/windows/Install-AIStation.ps1 | iex
  Or from an extracted release pack:
    .\Install-AIStation.ps1
#>

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/Ramtin-Karbaschi/ai-station.git"
$WslDistro = if ($env:AI_STATION_WSL_DISTRO) { $env:AI_STATION_WSL_DISTRO } else { "Ubuntu" }
$CloneDir = if ($env:AI_STATION_CLONE_DIR) { $env:AI_STATION_CLONE_DIR } else { "/tmp/ai-station-src" }

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
  throw "wsl.exe not found. Install WSL2 first."
}

Write-Host "AI Station Windows bootstrap" -ForegroundColor Cyan
Write-Host "Distro: $WslDistro"
Write-Host ""

Write-Host "0) Ensuring WSL2 stays alive (vmIdleTimeout=-1)..."
$WslConfig = Join-Path $env:USERPROFILE ".wslconfig"
$block = @"
[wsl2]
vmIdleTimeout=-1
"@
if (Test-Path $WslConfig) {
  $raw = Get-Content -Raw -Path $WslConfig
  if ($raw -notmatch '(?m)^\s*vmIdleTimeout\s*=\s*-1\s*$') {
    if ($raw -match '(?m)^\s*\[wsl2\]\s*$') {
      $raw = $raw -replace '(?m)^\s*vmIdleTimeout\s*=.*\r?\n', ''
      $raw = $raw -replace '(?m)^(\s*\[wsl2\]\s*\r?\n)', "`$1vmIdleTimeout=-1`r`n"
    } else {
      $raw = $raw.TrimEnd() + "`r`n`r`n" + $block + "`r`n"
    }
    Set-Content -Path $WslConfig -Value $raw -NoNewline
    Write-Host "Updated $WslConfig (vmIdleTimeout=-1). Run 'wsl --shutdown' once after install."
  } else {
    Write-Host "OK: vmIdleTimeout=-1 already in $WslConfig"
  }
} else {
  Set-Content -Path $WslConfig -Value ($block + "`r`n")
  Write-Host "Created $WslConfig"
}

Write-Host ""
Write-Host "1) Checking WSL prerequisites..."
wsl.exe -d $WslDistro -- bash -lc "set -e; command -v git; command -v docker; command -v nvidia-smi; nvidia-smi -L | head -1; docker compose version | head -1"

Write-Host ""
Write-Host "2) Cloning/updating repo and running install.sh inside WSL..."
# Pass paths as env vars to avoid nested-quoting bugs.
wsl.exe -d $WslDistro --env AI_STATION_REPO_URL=$RepoUrl --env AI_STATION_CLONE_DIR=$CloneDir -- bash -lc @'
set -euo pipefail
CLONE_DIR="${AI_STATION_CLONE_DIR:-/tmp/ai-station-src}"
REPO_URL="${AI_STATION_REPO_URL:-https://github.com/Ramtin-Karbaschi/ai-station.git}"
if [[ -d "$CLONE_DIR/.git" ]]; then
  git -C "$CLONE_DIR" fetch --prune origin
  git -C "$CLONE_DIR" checkout main
  git -C "$CLONE_DIR" pull --ff-only origin main
else
  rm -rf "$CLONE_DIR"
  git clone --branch main "$REPO_URL" "$CLONE_DIR"
fi
cd "$CLONE_DIR"
chmod +x scripts/install.sh scripts/ai scripts/*.sh 2>/dev/null || true
./scripts/install.sh --validate-only
sudo ./scripts/install.sh
'@

Write-Host ""
Write-Host "3) Installing Desktop launchers (thin trampolines to WSL /opt/ai-station)..."
$Desktop = [Environment]::GetFolderPath("Desktop")
$LauncherDir = Join-Path $Desktop "AI Station"
New-Item -ItemType Directory -Force -Path $LauncherDir | Out-Null
$DesktopWsl = (wsl.exe -d $WslDistro -- wslpath -a "$LauncherDir").Trim()
wsl.exe -d $WslDistro -- bash -lc "mkdir -p '$DesktopWsl' && cp -a '/opt/ai-station/AI Station/AI Station.cmd' '/opt/ai-station/AI Station/AI Station Manager.cmd' '$DesktopWsl'/"

# Keep a .ps1 name on Desktop for people who pin the old file, but never
# duplicate the control panel. Always re-enter the WSL copy.
$trampoline = @"
#Requires -Version 5.1
`$ErrorActionPreference = "Stop"
`$Distro = if (`$env:AI_STATION_WSL_DISTRO) { `$env:AI_STATION_WSL_DISTRO } else { "$WslDistro" }
`$Canonical = "\\wsl.localhost\`$Distro\opt\ai-station\AI Station\AI Station Manager.ps1"
if (-not (Test-Path -LiteralPath `$Canonical)) {
    Write-Host "AI Station is not installed in WSL at `$Canonical" -ForegroundColor Red
    [void](Read-Host "Press ENTER to close")
    exit 1
}
& `$Canonical @args
"@
Set-Content -LiteralPath (Join-Path $LauncherDir "AI Station Manager.ps1") -Value $trampoline -Encoding UTF8

# Remove leftover copies that used to shadow /opt/ai-station after upgrades.
@(
  (Join-Path $LauncherDir "AI Station.ps1"),
  (Join-Path $LauncherDir "AI Station Admin.cmd"),
  (Join-Path $Desktop "AI Station.cmd"),
  (Join-Path $Desktop "AI Station Manager.cmd"),
  (Join-Path $Desktop "AI Station Admin.cmd"),
  (Join-Path $Desktop "AI Station Manager.ps1"),
  (Join-Path $Desktop "AI Station.ps1")
) | ForEach-Object { Remove-Item -LiteralPath $_ -Force -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Open WebUI:  http://127.0.0.1:3000"
Write-Host "App API:     http://127.0.0.1:4000/v1"
Write-Host "Daily start: Desktop\AI Station\AI Station.cmd"
