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

$basePy = "C:\Users\Admin\AppData\Local\Programs\Python\Python314\python.exe"
if (-not (Test-Path $basePy)) { $basePy = (Get-Command python -ErrorAction SilentlyContinue).Source }
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

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
$vcvars = "C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $exe) -and -not $SkipBuild) {
    if (-not (Test-Path $vcvars)) { Fail "未找到 VS18 vcvars64.bat,无法编译(可自行拷贝 exe 后 -SkipBuild)"; exit 1 }
    Info "配置 CMake(首次)"
    $cache = Join-Path $root "server\build\CMakeCache.txt"
    if (-not (Test-Path $cache)) {
        cmd /c "cmake -B server\build -G Ninja -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$basePy"
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
