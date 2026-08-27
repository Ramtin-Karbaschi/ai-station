#Requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Distro = if ($env:AI_STATION_WSL_DISTRO) { $env:AI_STATION_WSL_DISTRO } else { "Ubuntu" }
$AiPath = "/opt/ai-station/scripts/ai"
$RepoPath = "\\wsl.localhost\$Distro\opt\ai-station"

function Invoke-AIStation {
    param([Parameter(Mandatory)][string[]]$AiArgs)
    Write-Host ""
    & wsl.exe -d $Distro --user root -- $AiPath @AiArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "AI Station command failed (exit $LASTEXITCODE)." -ForegroundColor Red
        if ($AiArgs.Count -gt 0 -and $AiArgs[0] -eq "start") {
            Write-Host "If Docker Desktop said ports are not available or /forwards/expose 500, restart Docker Desktop and try Start again." -ForegroundColor Yellow
        }
        return $false
    }
    return $true
}

function Wait-ForEnter {
    Write-Host ""
    [void](Read-Host "Press ENTER to continue")
}

function Read-SafeId {
    param([Parameter(Mandatory)][string]$Prompt)
    $value = (Read-Host $Prompt).Trim()
    if ($value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
        Write-Host "Use letters, numbers, dot, underscore, and hyphen." -ForegroundColor Yellow
        return $null
    }
    return $value
}

function Read-SafeRepo {
    param([Parameter(Mandatory)][string]$Prompt)
    $value = (Read-Host $Prompt).Trim()
    if ($value -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}/[A-Za-z0-9][A-Za-z0-9._-]{0,127}$') {
        Write-Host "Use org/name with letters, numbers, dot, underscore, and hyphen." -ForegroundColor Yellow
        return $null
    }
    return $value
}

function Read-SafeAbsPath {
    param([Parameter(Mandatory)][string]$Prompt)
    $value = (Read-Host $Prompt).Trim()
    if ($value -notmatch '^(/[A-Za-z0-9._-]+)+$') {
        Write-Host "Use an absolute path with letters, numbers, dot, underscore, and hyphen." -ForegroundColor Yellow
        return $null
    }
    return $value
}

function ConvertTo-WslUnc {
    param([Parameter(Mandatory)][string]$LinuxPath)
    $trimmed = $LinuxPath.Trim()
    if ($trimmed -match '^/mnt/([a-zA-Z])/(.*)$') {
        $drive = $Matches[1].ToUpper()
        $rest = $Matches[2] -replace '/', '\'
        return "${drive}:\${rest}"
    }
    $unc = $trimmed -replace '/', '\'
    return "\\wsl.localhost\$Distro$unc"
}

function Read-WslFolder {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Select an output folder"
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        return $null
    }
    $converted = & wsl.exe -d $Distro --user root -- wslpath -a $dialog.SelectedPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Could not convert that folder to a WSL path." -ForegroundColor Yellow
        return $null
    }
    $linux = ([string]$converted).Trim()
    if ($linux -notmatch '^(/[A-Za-z0-9._-]+)+$') {
        Write-Host "Use a folder path without spaces or unusual characters." -ForegroundColor Yellow
        return $null
    }
    return $linux
}

function Show-Menu {
    Clear-Host
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host "             AI Station Control Panel" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " Lifecycle"
    Write-Host "   1  Start                 2  Stop"
    Write-Host "   3  Restart               4  Status"
    Write-Host "   5  Verify                6  Open WebUI"
    Write-Host "   7  Open LiteLLM Admin    8  Open API health"
    Write-Host "   9  Open SearXNG"
    Write-Host "      Notebooks: Open WebUI -> Workspace -> Knowledge"
    Write-Host "      API keys:  option 22 (not document RAG)"
    Write-Host ""
    Write-Host " Runtime models (one heavy GPU profile at a time)"
    Write-Host "  10  List runtime models  11  Use general"
    Write-Host "  12  Use coder            13  Use reasoning"
    Write-Host "  14  Use vision           15  Use ornith"
    Write-Host "  16  Use qwen38           48  Use longwriter"
    Write-Host "  47  Stop heavy model"
    Write-Host ""
    Write-Host " Model storage (add / delete bytes)"
    Write-Host "  17  Catalog              18  Install curated id"
    Write-Host "  19  Add new Hugging Face model"
    Write-Host "  20  Remove to quarantine 21  Restore from quarantine"
    Write-Host ""
    Write-Host " Application API"
    Write-Host "  22  API info/projects    23  Create project key"
    Write-Host "  24  Show project         25  Revoke project key"
    Write-Host "  26  Open projects folder 27  LiteLLM UI login"
    Write-Host ""
    Write-Host " Clients"
    Write-Host "  28  OpenCode developer   29  Graphify status"
    Write-Host "  30  Graphify extract     42  Graphify map"
    Write-Host "  31  Run offline tests    32  Repair OpenCode WSL"
    Write-Host ""
    Write-Host " Operations"
    Write-Host "  33  Logs                 34  Backup"
    Write-Host "  35  Disk/Docker usage    36  Open in VS Code"
    Write-Host "  37  Git status           38  Reset WebUI password"
    Write-Host ""
    Write-Host " Media studio (ComfyUI)"
    Write-Host "  39  Start MiniMax media  40  Stop media / restore coder"
    Write-Host "  41  Open ComfyUI         43  Open media output"
    Write-Host "  44  Set media output     45  Set export folder"
    Write-Host "  46  Open export folder"
    Write-Host ""
    Write-Host " Automation (optional n8n)"
    Write-Host "  49  Start n8n            50  Stop n8n"
    Write-Host "  51  Open n8n"
    Write-Host ""
    Write-Host "   0  Exit"
    Write-Host ""
}

while ($true) {
    Show-Menu
    $choice = (Read-Host "Select").Trim()
    try {
        switch ($choice) {
            "0" { return }
            "1" { [void](Invoke-AIStation @("start")); Wait-ForEnter }
            "2" { [void](Invoke-AIStation @("stop")); Wait-ForEnter }
            "3" { [void](Invoke-AIStation @("restart")); Wait-ForEnter }
            "4" { [void](Invoke-AIStation @("status")); Wait-ForEnter }
            "5" { [void](Invoke-AIStation @("verify")); Wait-ForEnter }
            "6" { Start-Process "http://127.0.0.1:3000" }
            "7" { Start-Process "http://127.0.0.1:4000/ui" }
            "8" { Start-Process "http://127.0.0.1:4000/health/liveliness" }
            "9" { Start-Process "http://127.0.0.1:8889" }
            "10" { [void](Invoke-AIStation @("models-list")); Wait-ForEnter }
            "11" { [void](Invoke-AIStation @("models", "use", "general")); Wait-ForEnter }
            "12" { [void](Invoke-AIStation @("models", "use", "coder")); Wait-ForEnter }
            "13" { [void](Invoke-AIStation @("models", "use", "reasoning")); Wait-ForEnter }
            "14" { [void](Invoke-AIStation @("models", "use", "vision")); Wait-ForEnter }
            "15" { [void](Invoke-AIStation @("models", "use", "ornith")); Wait-ForEnter }
            "16" { [void](Invoke-AIStation @("models", "use", "qwen38")); Wait-ForEnter }
            "17" { [void](Invoke-AIStation @("models", "catalog")); Wait-ForEnter }
            "18" {
                $modelId = Read-SafeId "Manifest model id"
                if ($modelId) { [void](Invoke-AIStation @("models", "install", $modelId)) }
                Wait-ForEnter
            }
            "19" {
                $modelId = Read-SafeId "New model id"
                $repo = Read-SafeRepo "Hugging Face repo (org/name)"
                $filename = Read-SafeId "Exact filename"
                $role = Read-SafeId "Role (for example general)"
                $revision = Read-SafeId "Immutable revision SHA"
                if ($modelId -and $repo -and $filename -and $role -and $revision) {
                    Write-Host "Dry-run first. Nothing is written until you confirm."
                    [void](Invoke-AIStation @("models", "add", "--id", $modelId, "--repo", $repo, "--filename", $filename, "--role", $role, "--revision", $revision))
                    $sha = Read-SafeId "SHA-256 (64 hex chars)"
                    $size = Read-SafeId "Size in bytes"
                    if ($sha -and $size -and ((Read-Host "Type ADD to write the manifest") -ceq "ADD")) {
                        [void](Invoke-AIStation @("models", "add", "--id", $modelId, "--repo", $repo, "--filename", $filename, "--role", $role, "--revision", $revision, "--sha256", $sha, "--size-bytes", $size, "--confirm"))
                        if ((Read-Host "Type INSTALL to download now") -ceq "INSTALL") {
                            [void](Invoke-AIStation @("models", "install", $modelId))
                        }
                    }
                }
                Wait-ForEnter
            }
            "20" {
                $modelId = Read-SafeId "Manifest model id to quarantine"
                if ($modelId) {
                    [void](Invoke-AIStation @("models", "remove", $modelId))
                    if ((Read-Host "Type REMOVE to confirm the recoverable move") -ceq "REMOVE") {
                        [void](Invoke-AIStation @("models", "remove", $modelId, "--confirm"))
                    }
                }
                Wait-ForEnter
            }
            "21" {
                $modelId = Read-SafeId "Manifest model id to restore"
                if ($modelId -and (Read-Host "Type RESTORE to confirm") -ceq "RESTORE") {
                    [void](Invoke-AIStation @("models", "restore", $modelId, "--confirm"))
                }
                Wait-ForEnter
            }
            "22" { [void](Invoke-AIStation @("api-info")); Wait-ForEnter }
            "23" {
                $projectId = Read-SafeId "Project id (for example inventory-api)"
                if ($null -eq $projectId) { Wait-ForEnter; continue }
                $defaultModels = "Qwen3.8-27B-UD-Q4_K_M,Qwen3-Embedding-8B-Q4_K_M"
                $models = (Read-Host "Models CSV [$defaultModels]").Trim()
                if (-not $models) { $models = $defaultModels }
                if ($models -notmatch '^[A-Za-z0-9._,-]+$') {
                    Write-Host "Invalid model list." -ForegroundColor Yellow
                } else {
                    [void](Invoke-AIStation @("projects", "create", $projectId, "--models", $models))
                }
                Wait-ForEnter
            }
            "24" {
                $projectId = Read-SafeId "Project id"
                if ($projectId) { [void](Invoke-AIStation @("projects", "show-paths", $projectId)) }
                Wait-ForEnter
            }
            "25" {
                $projectId = Read-SafeId "Project id to revoke"
                if ($projectId) { [void](Invoke-AIStation @("projects", "revoke", $projectId)) }
                Wait-ForEnter
            }
            "26" { Start-Process "$RepoPath\projects" }
            "27" {
                [void](Invoke-AIStation @("litellm-ui-credentials"))
                Start-Process "http://127.0.0.1:4000/ui"
                Wait-ForEnter
            }
            "28" {
                if (Invoke-AIStation @("opencode", "doctor")) {
                    $desktop = Join-Path $env:LOCALAPPDATA "Programs\@opencode-aidesktop\OpenCode.exe"
                    if (Test-Path -LiteralPath $desktop) {
                        Write-Host "Launching OpenCode Desktop on the canonical WSL server..."
                        Start-Process -FilePath $desktop
                    } else {
                        Write-Host "Desktop app not found; launching the canonical WSL TUI..."
                        & wsl.exe -d $Distro -u aidev --cd /opt/ai-station -- `
                            env OPENCODE_EXPERIMENTAL_LSP_TOOL=true /usr/local/bin/opencode .
                    }
                }
                Wait-ForEnter
            }
            "29" { [void](Invoke-AIStation @("graphify", "status")); Wait-ForEnter }
            "30" { [void](Invoke-AIStation @("graphify", "extract", "--code-only")); Wait-ForEnter }
            "31" { [void](Invoke-AIStation @("test")); Wait-ForEnter }
            "32" {
                [void](Invoke-AIStation @("opencode", "install", "--create-user", "--own-project"))
                [void](Invoke-AIStation @("opencode", "configure"))
                [void](Invoke-AIStation @("opencode", "desktop", "configure"))
                [void](Invoke-AIStation @("opencode", "doctor"))
                Wait-ForEnter
            }
            "33" { [void](Invoke-AIStation @("logs", "snapshot", "all")); Wait-ForEnter }
            "34" { [void](Invoke-AIStation @("backup")); Wait-ForEnter }
            "35" { [void](Invoke-AIStation @("disk")); Wait-ForEnter }
            "36" { [void](Invoke-AIStation @("vscode")); Wait-ForEnter }
            "37" { [void](Invoke-AIStation @("git")); Wait-ForEnter }
            "38" { [void](Invoke-AIStation @("reset-webui-password")); Wait-ForEnter }
            "39" {
                [void](Invoke-AIStation @("provider", "start", "comfyui-media-experimental"))
                Wait-ForEnter
            }
            "40" {
                [void](Invoke-AIStation @("provider", "stop", "comfyui-media-experimental"))
                [void](Invoke-AIStation @("models", "use", "coder"))
                Wait-ForEnter
            }
            "41" { Start-Process "http://127.0.0.1:8188" }
            "42" {
                if (Invoke-AIStation @("graphify", "view")) {
                    Start-Process "http://127.0.0.1:4174"
                }
                Wait-ForEnter
            }
            "43" {
                $media = & wsl.exe -d $Distro --user root -- $AiPath output path media
                if ($LASTEXITCODE -eq 0 -and $media) {
                    Start-Process (ConvertTo-WslUnc ([string]$media).Trim())
                } else {
                    Write-Host "Could not resolve the media output folder." -ForegroundColor Yellow
                }
                Wait-ForEnter
            }
            "44" {
                $folder = Read-WslFolder
                if (-not $folder) { $folder = Read-SafeAbsPath "Linux media path under /srv/ai-station/runtime" }
                if ($folder) { [void](Invoke-AIStation @("output", "set", "media", $folder)) }
                Wait-ForEnter
            }
            "45" {
                $folder = Read-WslFolder
                if (-not $folder) { $folder = Read-SafeAbsPath "Export path" }
                if ($folder) { [void](Invoke-AIStation @("output", "set", "export", $folder)) }
                Wait-ForEnter
            }
            "46" {
                $export = & wsl.exe -d $Distro --user root -- $AiPath output path export
                if ($LASTEXITCODE -eq 0 -and $export) {
                    Start-Process (ConvertTo-WslUnc ([string]$export).Trim())
                } else {
                    Write-Host "Could not resolve the export folder." -ForegroundColor Yellow
                }
                Wait-ForEnter
            }
            "47" { [void](Invoke-AIStation @("models", "stop")); Wait-ForEnter }
            "48" { [void](Invoke-AIStation @("models", "use", "longwriter")); Wait-ForEnter }
            "49" { [void](Invoke-AIStation @("n8n", "start")); Wait-ForEnter }
            "50" { [void](Invoke-AIStation @("n8n", "stop")); Wait-ForEnter }
            "51" { Start-Process "http://127.0.0.1:5678" }
            default { Write-Host "Unknown selection." -ForegroundColor Yellow; Start-Sleep -Seconds 1 }
        }
    } catch {
        Write-Host $_.Exception.Message -ForegroundColor Red
        Wait-ForEnter
    }
}
