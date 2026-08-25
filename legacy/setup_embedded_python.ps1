param(
    [string]$PyVersion = "3.14.2",
    [string]$TargetDir = "$PSScriptRoot\python_embed"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Setup Embedded Python $PyVersion" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Derive correct short version: "3.14" -> "314"
$parts = $PyVersion -split '\.'
$PyMajorMinor = "$($parts[0]).$($parts[1])"
$PyShort = "$($parts[0])$($parts[1])"

$EmbedUrl = "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$PipIndex = "https://pypi.tuna.tsinghua.edu.cn/simple"

if (Test-Path $TargetDir) {
    Write-Host "[Clean] Removing old $TargetDir" -ForegroundColor Yellow
    Remove-Item -Recurse -Force $TargetDir
}
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

$ZipFile = Join-Path $env:TEMP "python-$PyVersion-embed-amd64.zip"

# 1. Download embedded Python
Write-Host "[Download] Python $PyVersion embeddable..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri $EmbedUrl -OutFile $ZipFile -UseBasicParsing
} catch {
    Write-Host "ERROR: Failed to download. Check network." -ForegroundColor Red
    exit 1
}

# 2. Extract
Write-Host "[Extract] To $TargetDir" -ForegroundColor Yellow
Expand-Archive -Path $ZipFile -DestinationPath $TargetDir -Force
Remove-Item $ZipFile -Force

# 3. Configure _pth file (python314._pth, NOT python3142._pth)
$PthFile = Join-Path $TargetDir "python$PyShort._pth"
Write-Host "[Config] $PthFile" -ForegroundColor Yellow

$pthContent = @"
python$PyShort.zip
.
Lib\site-packages

import site
"@
$pthContent | Out-File -FilePath $PthFile -Encoding ASCII

# 4. Clean up any stale files from previous runs
$wrongPth = Join-Path $TargetDir "python${PyShort}2._pth"
$wrongZip = Join-Path $TargetDir "python${PyShort}2.zip"
if (Test-Path $wrongPth) { Remove-Item $wrongPth -Force }
if (Test-Path $wrongZip) { Remove-Item $wrongZip -Force }

# 5. Install pip
Write-Host "[Install] pip..." -ForegroundColor Yellow
$GetPipFile = Join-Path $env:TEMP "get-pip.py"
Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipFile -UseBasicParsing

$PyExe = Join-Path $TargetDir "python.exe"
& $PyExe $GetPipFile --no-warn-script-location
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed" -ForegroundColor Red
    exit 1
}
Remove-Item $GetPipFile -Force

# 6. Install packages into embedded Lib\site-packages (--target to avoid system site-packages)
$SitePkg = Join-Path $TargetDir "Lib\site-packages"
Write-Host "[Install] numpy geopack requests (from Tsinghua mirror)..." -ForegroundColor Yellow
& $PyExe -m pip install --target="$SitePkg" -i $PipIndex --no-warn-script-location numpy geopack requests
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Package install failed" -ForegroundColor Red
    exit 1
}

# 7. Verify
Write-Host "[Verify] Testing imports..." -ForegroundColor Yellow
& $PyExe -c "import numpy, geopack, requests; print('numpy', numpy.__version__, '| geopack OK | requests OK')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Import verification failed" -ForegroundColor Red
    exit 1
}

# 8. Cleanup pip cache and __pycache__
$pycache = Join-Path $TargetDir "Lib\site-packages\__pycache__"
if (Test-Path $pycache) { Remove-Item -Recurse -Force $pycache }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  SUCCESS" -ForegroundColor Green
Write-Host "  Embedded Python ready at: $TargetDir" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Cyan
