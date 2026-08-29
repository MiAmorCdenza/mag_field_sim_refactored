# mf_server 一键启动 + 简易展示。
#
# 自动完成:venv 创建/依赖安装 → CMake 配置/编译 → 端口预检 →
# 启动服务器 → 等待就绪 → 打开浏览器。
#
# 用法:
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
#   scripts\start.bat                          (双击)
# 参数:
#   -Port 8001 -Particles 20000 -Graph graphs\default_graph.json
#   -SkipBuild(不编译) -NoBrowser(不自动开浏览器) -JustCheck(只做环境检查)
param(
    [int]$Port = 8001,
    [int]$Particles = 20000,
    [string]$Graph = "graphs\default_graph.json",
    [switch]$SkipBuild,
    [switch]$NoBrowser,
    [switch]$JustCheck
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Info($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  ok: $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "  FAIL: $msg" -ForegroundColor Red }

# ---------- 1. 环境审计 ----------
if ($JustCheck) {
    & (Join-Path $PSScriptRoot "check_env.ps1")
    exit $LASTEXITCODE
}

# ---- 机器无关的路径发现(可迁移性)----
function Find-Python314 {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        $exe = & py -3.14 -c "import sys;print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return $exe }
    }
    foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
                     "C:\Python314\python.exe",
                     "C:\Program Files\Python314\python.exe")) {
        if (Test-Path $p) { return $p }
    }
    $c = Get-Command python -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    return $null
}

function Find-VcVars {
    $vsw = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if (Test-Path $vsw) {
        $vs = & $vsw -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null
        if ($vs) {
            $p = Join-Path $vs "VC\Auxiliary\Build\vcvars64.bat"
            if (Test-Path $p) { return $p }
        }
    }
    foreach ($e in @("Community", "Professional", "Enterprise", "BuildTools")) {
        $p = "C:\Program Files\Microsoft Visual Studio\2022\$e\VC\Auxiliary\Build\vcvars64.bat"
        if (Test-Path $p) { return $p }
    }
    $p18 = "C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Auxiliary\Build\vcvars64.bat"
    if (Test-Path $p18) { return $p18 }
    return $null
}

$basePy = Find-Python314
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not $basePy) {
    Fail "未找到 Python 3.14(请安装 python.org 3.14 或 py 启动器)"
    exit 1
}

# ---------- 2. venv 自动创建 + 依赖 ----------
if (-not (Test-Path $venvPy)) {
    Info "创建虚拟环境(.venv,Python 3.14)"
    & $basePy -m venv (Join-Path $root ".venv")
    if (-not (Test-Path $venvPy)) { Fail "venv 创建失败"; exit 1 }
    Ok "venv 已创建"
}
Info "检查 venv 依赖(numpy/geopack/websockets/requests)"
$missing = @()
foreach ($p in @("numpy", "geopack", "websockets", "requests")) {
    & $venvPy -m pip show $p *> $null
    if ($LASTEXITCODE -ne 0) { $missing += $p }
}
if ($missing.Count -gt 0) {
    Info "安装缺失依赖: $($missing -join ', ')"
    & $venvPy -m pip install @missing
    if ($LASTEXITCODE -ne 0) { Fail "依赖安装失败"; exit 1 }
    Ok "依赖已安装"
} else {
    Ok "依赖齐全"
}

# ---------- 3. 服务器二进制(缺则配置+编译) ----------
$exe = Join-Path $root "server\build\mf_server.exe"
$vcvars = Find-VcVars
if (-not (Test-Path $exe) -and -not $SkipBuild) {
    if (-not $vcvars) { Fail "未找到 MSVC vcvars64.bat,无法编译(可自行拷贝 exe 后 -SkipBuild)"; exit 1 }
    Info "配置 CMake(首次)"
    $cache = Join-Path $root "server\build\CMakeCache.txt"
    if (-not (Test-Path $cache)) {
        cmd /c "call `"$vcvars`" >nul 2>&1 && cmake -S server -B server\build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$basePy"
        if ($LASTEXITCODE -ne 0) { Fail "CMake 配置失败"; exit 1 }
    }
    Info "编译服务器(Release)"
    cmd /c "call `"$vcvars`" >nul 2>&1 && cmake --build server\build"
    if ($LASTEXITCODE -ne 0) { Fail "编译失败"; exit 1 }
    Ok "编译完成"
} elseif (Test-Path $exe) {
    Ok "服务器二进制已就绪(如需重编译请先停止 mf_server)"
}

# ---------- 4. 端口/运行实例预检 ----------
$srv = Get-Process mf_server -ErrorAction SilentlyContinue
if ($srv) {
    Info "mf_server 已在运行(PID $($srv.Id -join ',')) —— 直接打开浏览器"
} else {
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        Fail "端口 $Port 已被其它进程占用(Owner PID $($busy.OwningProcess -join ','))"; exit 1
    }
    $graphArg = if (Test-Path (Join-Path $root $Graph)) { Join-Path $root $Graph } else { "" }
    Info "启动服务器(端口 $Port,粒子 $Particles,图 $graphArg)"
    if ($graphArg) {
        Start-Process -FilePath $exe -ArgumentList "--root","$root","--port","$Port","--particles","$Particles","--graph",$graphArg -WorkingDirectory $root
    } else {
        Start-Process -FilePath $exe -ArgumentList "--root","$root","--port","$Port","--particles","$Particles" -WorkingDirectory $root
    }
}

# ---------- 5. 等待就绪 ----------
Info "等待服务器就绪(最长 60s,粗点阵烘焙约 12s)"
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/graph" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
if (-not $ready) { Fail "服务器未就绪,查看 logs\server.jsonl"; exit 1 }
Ok "服务器就绪"

# ---------- 6. 打开浏览器 ----------
if (-not $NoBrowser) {
    Info "打开浏览器 http://127.0.0.1:$Port/"
    Start-Process "http://127.0.0.1:$Port/"
}
Write-Host "`n启动完成。停止服务器: Get-Process mf_server | Stop-Process`n"
