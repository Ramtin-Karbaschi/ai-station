#Requires -Version 5.1
$ErrorActionPreference = "Stop"

# AI Station quick-start (Windows)
# Starts the platform, waits until Open WebUI is ready, opens the DEFAULT browser.
# Leaves the platform running (stop via Manager).

$Distro = if ($env:AI_STATION_WSL_DISTRO) { $env:AI_STATION_WSL_DISTRO } else { "Ubuntu" }
$AiPath = "/opt/ai-station/scripts/ai"
$Url = "http://127.0.0.1:3000"

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
& wsl.exe -d $Distro --user root -- $AiPath start
if ($LASTEXITCODE -ne 0) {
    throw "AI Station start failed (exit $LASTEXITCODE). If Docker Desktop reported /forwards/expose 500, restart Docker Desktop and retry."
}

Wait-OpenWebUI

Write-Host "Opening Open WebUI in your default browser..."
Write-Host "URL: $Url"
Write-Host ""
Write-Host "Sign in with your local Open WebUI account."
Write-Host "Notebooks: Workspace > Knowledge. API keys are Manager option 22."
Write-Host ""
Write-Host "If the password is rejected, open AI Station Manager.cmd"
Write-Host "and choose: 38. Reset Open WebUI password"
Start-Process $Url

Write-Host ""
Write-Host "AI Station is RUNNING and will stay up."
Write-Host "To stop later: AI Station Manager.cmd -> Stop"
Write-Host ""
Write-Host "Press ENTER to close this window (platform keeps running)."
Read-Host | Out-Null
