# FreeCAD MCP - Dell Machine Setup Script
# Run this once from PowerShell to install the addon and configure Claude Desktop.
# Right-click this file and choose "Run with PowerShell", or run:
#   powershell -ExecutionPolicy Bypass -File "C:\Users\AXIO\OneDrive\Documents\freecad-mcp\setup-mcp-dell.ps1"

$ErrorActionPreference = "Stop"

$sourceAddon   = "$env:USERPROFILE\OneDrive\Documents\freecad-mcp\addon\FreeCADMCP"
$freecadModDir = "$env:APPDATA\FreeCAD\Mod"
$addonDest     = "$freecadModDir\FreeCADMCP"
$claudeConfig  = "$env:LOCALAPPDATA\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json"
$projectDir    = "$env:USERPROFILE\OneDrive\Documents\freecad-mcp"

# ── 1. Install FreeCAD addon ──────────────────────────────────────────────────
Write-Host "`n[1/2] Installing FreeCADMCP addon..." -ForegroundColor Cyan

if (-not (Test-Path $freecadModDir)) {
    New-Item -ItemType Directory -Path $freecadModDir -Force | Out-Null
    Write-Host "  Created: $freecadModDir"
}

if (Test-Path $addonDest) {
    Remove-Item -Recurse -Force $addonDest
    Write-Host "  Removed old addon at: $addonDest"
}

Copy-Item -Recurse -Force $sourceAddon $addonDest
Write-Host "  Copied addon to: $addonDest" -ForegroundColor Green

# ── 2. Configure Claude Desktop ───────────────────────────────────────────────
Write-Host "`n[2/2] Configuring Claude Desktop..." -ForegroundColor Cyan

$newEntry = @{
    freecad = @{
        command = "uv"
        args    = @("--directory", $projectDir, "run", "freecad-mcp")
    }
}

if (Test-Path $claudeConfig) {
    $existing = Get-Content $claudeConfig -Raw | ConvertFrom-Json
    if (-not $existing.mcpServers) {
        $existing | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
    }
    $existing.mcpServers | Add-Member -NotePropertyName "freecad" -NotePropertyValue $newEntry.freecad -Force
    $existing | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
    Write-Host "  Updated existing config: $claudeConfig" -ForegroundColor Green
} else {
    $claudeDir = Split-Path $claudeConfig
    if (-not (Test-Path $claudeDir)) {
        New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null
        Write-Host "  Created directory: $claudeDir"
    }
    $config = @{ mcpServers = $newEntry }
    $config | ConvertTo-Json -Depth 10 | Set-Content $claudeConfig -Encoding UTF8
    Write-Host "  Created new config: $claudeConfig" -ForegroundColor Green
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Next steps:"
Write-Host "  1. Open FreeCAD"
Write-Host "  2. Switch to the 'MCP Addon' workbench"
Write-Host "  3. Click 'Start RPC Server' in the FreeCAD MCP toolbar"
Write-Host "  4. Restart Claude Desktop - the 'freecad' MCP will appear"
Write-Host ""
Read-Host "Press Enter to close"
