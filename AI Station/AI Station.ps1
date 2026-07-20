$ErrorActionPreference = "Stop"

# AI Station quick-start (Windows)
# Starts the platform, waits until Open WebUI is ready, opens the DEFAULT browser.
# Leaves the platform running (stop via Manager).

$Distro = "Ubuntu"
$Url = "http://127.0.0.1:3000"
$StartScript = "/opt/ai-station/scripts/ai-station-user-start.sh"

function Invoke-WslBash {
    param([string]$Command)
    & wsl.exe -d $Distro --user root -- bash -lc $Command
    if ($LASTEXITCODE -ne 0) {
        throw "WSL command failed: $Command"
    }
}

function Wait-OpenWebUI {
    Write-Host "Waiting for Open WebUI to become ready..."
    for ($i = 1; $i -le 90; $i++) {
        try {
            $resp = Invoke-WebRequest -Uri "$Url/api/config" -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) {
                Write-Host "Open WebUI is ready."
                return
            }
        } catch {
            # keep waiting
        }
        Start-Sleep -Seconds 2
    }
    throw "Open WebUI did not become ready on $Url"
}

Write-Host "Starting AI Station..."
Invoke-WslBash $StartScript

Wait-OpenWebUI

Write-Host "Opening Open WebUI in your default browser..."
Write-Host "URL: $Url"
Write-Host ""
Write-Host "Login email on this workstation:"
Write-Host "  ramtin.karbaschi@gmail.com"
Write-Host ""
Write-Host "If the password is rejected, open AI Station Manager.cmd"
Write-Host "and choose: 26. Reset Open WebUI password"
Start-Process $Url

Write-Host ""
Write-Host "AI Station is RUNNING and will stay up."
Write-Host "To stop later: AI Station Manager.cmd -> Stop"
Write-Host ""
Write-Host "Press ENTER to close this window (platform keeps running)."
Read-Host | Out-Null
