param(
    [string]$OutputDir = "$PSScriptRoot\deploy_package"
)

$ErrorActionPreference = "Stop"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  EarthMagFieldSim Deploy Packer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}

$targetDir = Join-Path $OutputDir "EarthMagFieldSim"
New-Item -ItemType Directory -Force -Path (Join-Path $targetDir "static") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $targetDir "python_embed") | Out-Null

$files = @(
    @{src="build\Release\MagFieldSim_Server.exe"; dst="MagFieldSim_Server.exe"},
    @{src="python_bridge.py"; dst="python_bridge.py"},
    @{src="config.json"; dst="config.json"},
    @{src="run.bat"; dst="run.bat"},
    @{src="static\index.html"; dst="static\index.html"},
    @{src="static\main.js"; dst="static\main.js"}
)

Write-Host "[Packing core files]" -ForegroundColor Yellow
foreach ($entry in $files) {
    $src = Join-Path $PSScriptRoot $entry.src
    $dst = Join-Path $targetDir $entry.dst
    $dstDir = Split-Path $dst -Parent
    if (!(Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $dst -Force
        Write-Host "  + $($entry.dst)" -ForegroundColor Green
    } else {
        Write-Host "  ! MISSING: $($entry.src)" -ForegroundColor Red
    }
}

# Copy embedded Python runtime
$pyEmbedSrc = Join-Path $PSScriptRoot "python_embed"
$pyEmbedDst = Join-Path $targetDir "python_embed"
if (Test-Path $pyEmbedSrc) {
    Write-Host "[Packing embedded Python]" -ForegroundColor Yellow
    Copy-Item -Path "$pyEmbedSrc\*" -Destination $pyEmbedDst -Recurse -Force
    Write-Host "  + python_embed\" -ForegroundColor Green
} else {
    Write-Host "  ! MISSING: python_embed\ (run setup_embedded_python.ps1 first)" -ForegroundColor Red
}

$readme = @'
================================================================
  EarthMagFieldSim - Deployment Guide
================================================================

[Prerequisites on target machine]

Visual C++ Redistributable (x64) ONLY:
  https://aka.ms/vs/17/release/vc_redist.x64.exe

Python is BUNDLED - no Python installation required!

[Steps]

1. Copy the entire "EarthMagFieldSim" folder to target machine.
2. Double-click "run.bat" to start.
3. Open browser at http://localhost:8001

First launch takes ~30 seconds to compute the magnetic field grid.
Subsequent launches start instantly.

[Troubleshooting]

If run.bat does nothing or crashes:
- Install vc_redist.x64.exe (Visual C++ Redistributable)
- Open cmd in the folder, run "run.bat" manually to see errors

================================================================
'@
$readme | Out-File -FilePath (Join-Path $targetDir "README.txt") -Encoding ASCII

$zipPath = Join-Path $OutputDir "EarthMagFieldSim.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

Write-Host ""
Write-Host "[Compressing]" -ForegroundColor Yellow
Compress-Archive -Path $targetDir -DestinationPath $zipPath -Force

$sizeKb = [math]::Round((Get-Item $zipPath).Length / 1KB, 1)
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SUCCESS" -ForegroundColor Green
Write-Host "  File: $zipPath" -ForegroundColor White
Write-Host "  Size: ${sizeKb} KB" -ForegroundColor White
Write-Host "  Folder: $targetDir\" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Copy EarthMagFieldSim.zip to target machine and extract." -ForegroundColor Yellow
