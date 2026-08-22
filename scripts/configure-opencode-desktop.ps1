[CmdletBinding()]
param(
    [string]$ServerUrl = "http://127.0.0.1:4096"
)

$ErrorActionPreference = "Stop"
$settingsPath = Join-Path $env:APPDATA "ai.opencode.desktop\opencode.settings"
$settingsDirectory = Split-Path -Parent $settingsPath
New-Item -ItemType Directory -Path $settingsDirectory -Force | Out-Null

$settings = if (Test-Path -LiteralPath $settingsPath) {
    Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
} else {
    [pscustomobject]@{}
}
$settings | Add-Member -NotePropertyName defaultServerUrl -NotePropertyValue $ServerUrl -Force
$settingsJson = $settings | ConvertTo-Json -Depth 20
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($settingsPath, $settingsJson + [Environment]::NewLine, $utf8NoBom)

$globalPath = Join-Path $settingsDirectory "opencode.global.dat"
$global = if (Test-Path -LiteralPath $globalPath) {
    Get-Content -LiteralPath $globalPath -Raw | ConvertFrom-Json
} else {
    [pscustomobject]@{}
}
$projectRoot = "/opt/ai-station"
$projectsByServer = [ordered]@{}
$projectsByServer[$ServerUrl] = @(@{ worktree = $projectRoot; expanded = $true })
$lastProjectByServer = [ordered]@{}
$lastProjectByServer[$ServerUrl] = $projectRoot
$serverState = [ordered]@{
    list = @($ServerUrl)
    projects = $projectsByServer
    lastProject = $lastProjectByServer
    recentlyClosed = @{}
}
$global | Add-Member -NotePropertyName server -NotePropertyValue ($serverState | ConvertTo-Json -Depth 10 -Compress) -Force
$globalJson = $global | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($globalPath, $globalJson + [Environment]::NewLine, $utf8NoBom)

# Existing Desktop tabs retain the server that created them. A stale native
# sidecar tab therefore overrides defaultServerUrl and silently routes prompts
# away from the canonical WSL server. Preserve the old window state, then open
# a clean remote draft instead of trying to reuse sidecar-only session IDs.
$windowBackupStamp = Get-Date -Format "yyyyMMddHHmmss"
$migratedWindows = 0
Get-ChildItem -LiteralPath $settingsDirectory -Filter "opencode.window.*.dat" -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        $windowPath = $_.FullName
        $windowState = Get-Content -LiteralPath $windowPath -Raw | ConvertFrom-Json
        $tabsProperty = $windowState.PSObject.Properties["tabs"]
        if ($null -eq $tabsProperty -or [string]::IsNullOrWhiteSpace([string]$tabsProperty.Value)) {
            return
        }
        $tabs = @($tabsProperty.Value | ConvertFrom-Json)
        $hasNativeSidecarTab = @($tabs | Where-Object { $_.server -eq "sidecar" }).Count -gt 0
        $hasMalformedRemoteTabs = -not ([string]$tabsProperty.Value).TrimStart().StartsWith("[") -and
            @($tabs | Where-Object { $_.server -eq $ServerUrl }).Count -gt 0
        if (-not $hasNativeSidecarTab -and -not $hasMalformedRemoteTabs) {
            return
        }

        Copy-Item -LiteralPath $windowPath -Destination "$windowPath.bak-$windowBackupStamp" -Force
        $draftId = [guid]::NewGuid().ToString()
        $remoteTabs = @(
            [ordered]@{
                type = "draft"
                draftID = $draftId
                server = $ServerUrl
                directory = $projectRoot
            }
        )
        $remoteTabsJson = ConvertTo-Json -InputObject $remoteTabs -Depth 10 -Compress
        $windowState | Add-Member -NotePropertyName "tabs" -NotePropertyValue $remoteTabsJson -Force
        $windowState | Add-Member -NotePropertyName "tabs.recent" -NotePropertyValue (@{ key = "draft:$draftId" } | ConvertTo-Json -Compress) -Force
        $windowState | Add-Member -NotePropertyName "tabs.info" -NotePropertyValue "{}" -Force
        $windowState | Add-Member -NotePropertyName "tabs.closed" -NotePropertyValue "[]" -Force
        $windowJson = $windowState | ConvertTo-Json -Depth 20
        [System.IO.File]::WriteAllText($windowPath, $windowJson + [Environment]::NewLine, $utf8NoBom)
        $script:migratedWindows += 1
    }

$nativeConfig = Join-Path $env:USERPROFILE ".config\opencode"
New-Item -ItemType Directory -Path $nativeConfig -Force | Out-Null
$resolvedNativeConfig = [System.IO.Path]::GetFullPath($nativeConfig).TrimEnd('\')
foreach ($relative in @("agents", "commands", "plugins")) {
    $target = [System.IO.Path]::GetFullPath((Join-Path $resolvedNativeConfig $relative))
    if (-not $target.StartsWith($resolvedNativeConfig + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the native OpenCode config root: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

Get-ChildItem -LiteralPath $resolvedNativeConfig -Filter "opencode.jsonc.bak-*" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force

$nativeGuard = [ordered]@{
    '$schema' = "https://opencode.ai/config.json"
    enabled_providers = @("ai-station")
    model = "ai-station/Qwen3-Coder-30B-A3B-Instruct-Q4"
    small_model = "ai-station/Qwen3-Coder-30B-A3B-Instruct-Q4"
    default_agent = "build"
    share = "disabled"
    autoupdate = $false
    permission = [ordered]@{
        read = "allow"
        glob = "allow"
        grep = "allow"
        list = "allow"
        edit = "deny"
        bash = "deny"
        external_directory = "deny"
        webfetch = "deny"
        websearch = "deny"
    }
    compaction = [ordered]@{ auto = $true; prune = $true; reserved = 2048 }
    provider = [ordered]@{
        "ai-station" = [ordered]@{
            npm = "@ai-sdk/openai-compatible"
            name = "AI Station (native sidecar disabled)"
            options = [ordered]@{
                baseURL = "http://127.0.0.1:4000/v1"
                apiKey = "native-sidecar-disabled-use-wsl-server"
                timeout = 600000
            }
            models = [ordered]@{
                "Qwen3-Coder-30B-A3B-Instruct-Q4" = [ordered]@{
                    name = "Qwen3 Coder"
                    tool_call = $true
                    limit = [ordered]@{ context = 16384; output = 4096 }
                }
                "Qwen3.6-35B-A3B-UD-Q4_K_M" = [ordered]@{
                    name = "Qwen3.6 General"
                    tool_call = $true
                    limit = [ordered]@{ context = 8192; output = 2048 }
                }
                "DeepSeek-R1-Distill-Qwen-32B-Q4_K_M" = [ordered]@{
                    name = "DeepSeek R1 Reasoning"
                    reasoning = $true
                    tool_call = $false
                    limit = [ordered]@{ context = 8192; output = 2048 }
                }
                "Ornith-1.5-35B-Q4_K_M" = [ordered]@{
                    name = "Ornith Coding"
                    tool_call = $true
                    limit = [ordered]@{ context = 8192; output = 2048 }
                }
            }
        }
    }
    agent = [ordered]@{
        build = [ordered]@{
            steps = 1
            permission = [ordered]@{ edit = "deny"; bash = "deny"; external_directory = "deny" }
        }
    }
}
$nativeGuardPath = Join-Path $resolvedNativeConfig "opencode.jsonc"
$nativeGuardJson = $nativeGuard | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($nativeGuardPath, $nativeGuardJson + [Environment]::NewLine, $utf8NoBom)

$nativeAgents = @"
# Native OpenCode sidecar guard

This Windows-native sidecar is intentionally non-operational. Use the Desktop
connection named `127.0.0.1:4096`, which runs the canonical AI Station OpenCode
server as `aidev` inside WSL. Do not execute development tasks, serve Windows
Desktop directories, or claim completion from this sidecar.
"@
[System.IO.File]::WriteAllText((Join-Path $resolvedNativeConfig "AGENTS.md"), $nativeAgents, $utf8NoBom)

Write-Output "OK: OpenCode Desktop defaults to $ServerUrl"
Write-Output "OK: Desktop project root is $projectRoot on the WSL server"
Write-Output "OK: migrated $migratedWindows native-sidecar window state(s) to the WSL server"
Write-Output "OK: native sidecar config is sanitized and non-operational"
