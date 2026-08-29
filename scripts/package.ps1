# 便携包打包:Release exe + 嵌入式 Python 运行时 + 站点包 → zip。
# 目标机器无需 Python/VS,仅需 Windows x64(Release CRT 已随包附带)。
#
# 用法: powershell -ExecutionPolicy Bypass -File scripts\package.ps1 [-Version v0.1.0-beta]
param([string]$Version = "v0.1.0-beta")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Info($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg) { Write-Host "  ok: $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "  FAIL: $msg" -ForegroundColor Red }

# ---- 机器无关的路径发现(与 start.ps1/check_env.ps1 同源)----
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
$vcvars = Find-VcVars

# ---------- 1. 前置资产检查(+ embed 自举) ----------
Info "前置检查"
if (-not $basePy) { Fail "未找到 Python 3.14"; exit 1 }
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { Fail "缺少 .venv —— 先运行 scripts\start.ps1 建立环境"; exit 1 }

# python_embed 缺失/不完整时,从本机 Python 3.14 自举
# (复制 DLL + 标准库 + 生成 _pth —— 新开发机可复现打包)
$embed = Join-Path $root "python_embed"
$pth = Join-Path $embed "python314._pth"
if (-not (Test-Path $embed) -or -not (Test-Path $pth) -or
    -not (Test-Path (Join-Path $embed "Lib\encodings"))) {
    Info "python_embed 不完整,从本机 Python 自举"
    $pyHome = Split-Path -Parent $basePy
    New-Item -ItemType Directory -Path $embed -Force | Out-Null
    foreach ($f in @("python314.dll", "python3.dll", "vcruntime140.dll",
                     "vcruntime140_1.dll", "sqlite3.dll", "libffi-8.dll",
                     "libcrypto-3.dll", "libssl-3.dll", "LICENSE.txt",
                     "python.cat")) {
        $src = Join-Path $pyHome $f
        if (Test-Path $src) { Copy-Item $src $embed -Force }
    }
    # 标准库必须进 Lib(排除 site-packages,后者由打包步骤单独填)
    # msvcp140:numpy 等 C++ 扩展的运行库(VC redist 组件)
    $msvcp = "C:\Windows\System32\msvcp140.dll"
    if (-not (Test-Path $msvcp)) {
        $crt = Get-ChildItem "C:\Program Files\Microsoft Visual Studio" -Recurse -Filter "msvcp140.dll" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "x64\\Microsoft\.VC.*CRT" } | Select-Object -First 1
        if ($crt) { $msvcp = $crt.FullName }
    }
    if (Test-Path $msvcp) { Copy-Item $msvcp $embed -Force }

    if (-not (Test-Path (Join-Path $embed "DLLs"))) {
        Copy-Item (Join-Path $pyHome "DLLs") (Join-Path $embed "DLLs") -Recurse -Force
    }

    if (-not (Test-Path (Join-Path $embed "Lib\encodings"))) {
        New-Item -ItemType Directory -Path (Join-Path $embed "Lib") -Force | Out-Null
        Get-ChildItem (Join-Path $pyHome "Lib") | Where-Object { $_.Name -ne "site-packages" } | ForEach-Object {
            Copy-Item $_.FullName (Join-Path $embed "Lib") -Recurse -Force
        }
    }
    @"
python314.zip
.
DLLs
Lib
Lib\site-packages

"@ | Set-Content -Path $pth -Encoding ASCII
    Ok "python_embed 已自举"
}
Ok "前置资产齐备(python_embed + .venv)"

# ---------- 2. Release 构建(独立目录,不碰开发构建) ----------
Info "Release 构建(server/build_rel)"
$relDir = Join-Path $root "server\build_rel"
$relCache = Join-Path $relDir "CMakeCache.txt"
if (-not (Test-Path $relCache)) {
    cmd /c "call `"$vcvars`" >nul 2>&1 && cmake -S server -B server\build_rel -G Ninja -DCMAKE_BUILD_TYPE=Release -DPython3_EXECUTABLE=$basePy"
    if ($LASTEXITCODE -ne 0) { Fail "CMake 配置失败"; exit 1 }
}
if (-not $vcvars) { Fail "未找到 MSVC vcvars64.bat"; exit 1 }
cmd /c "call `"$vcvars`" >nul 2>&1 && cmake --build server\build_rel"
if ($LASTEXITCODE -ne 0) { Fail "Release 编译失败"; exit 1 }
Ok "Release 构建完成"

# ---------- 3. 组装便携目录 ----------
Info "组装便携目录"
$pkg = Join-Path $root "dist\mf_server_portable"
if (Test-Path $pkg) { Remove-Item $pkg -Recurse -Force }
New-Item -ItemType Directory -Path $pkg | Out-Null

# exe 与嵌入式 Python(._pth 必须与 exe 同目录)
Copy-Item (Join-Path $relDir "mf_server.exe") $pkg
# embed 的 Lib 只带标准库;site-packages 由下方从 venv 精确拷贝
# (embed 自带旧版包/scipy 等杂物,不带过来)
Get-ChildItem $embed | ForEach-Object {
    $dst2 = Join-Path $pkg $_.Name
    if ($_.Name -eq "Lib") {
        New-Item -ItemType Directory -Path $dst2 -Force | Out-Null
        Get-ChildItem $_.FullName | Where-Object { $_.Name -ne "site-packages" } | ForEach-Object {
            Copy-Item $_.FullName $dst2 -Recurse -Force
        }
    } else {
        Copy-Item $_.FullName $dst2 -Recurse
    }
}
# 服务器运行所需站点包(numpy 二进制 + geopack 纯 python;requests/websockets 仅测试用)
$sp = Join-Path $pkg "Lib\site-packages"
foreach ($m in @("numpy", "scipy", "geopack")) {
    # 先清后拷:python_embed 自带旧版包,合并会混版本;
    # 用 robocopy:Copy-Item -Recurse 不复制隐藏项(numpy.libs 是隐藏
    # 目录,漏拷 openblas → "DLL load failed")
    $dst = Join-Path $sp $m
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Copy-Item (Join-Path $root ".venv\Lib\site-packages\$m") $dst -Recurse
    # numpy 2.x 的 $m.libs 是 site-packages 下的同级目录(不是包内子目录)!
    # 漏拷同级目录 → openblas 缺失 → "DLL load failed"
    $libsSrc = Join-Path $root ".venv\Lib\site-packages\$m.libs"
    if (Test-Path $libsSrc) {
        $libsDst = Join-Path $sp "$m.libs"
        if (Test-Path $libsDst) { Remove-Item $libsDst -Recurse -Force }
        Copy-Item $libsSrc $libsDst -Recurse
    }
}
# 应用 Python 代码(引擎与节点插件 —— 服务器在 --root 下 import engine)
Copy-Item (Join-Path $root "engine") (Join-Path $pkg "engine") -Recurse
Copy-Item (Join-Path $root "nodes") (Join-Path $pkg "nodes") -Recurse
if (Test-Path (Join-Path $root "user_nodes")) {
    Copy-Item (Join-Path $root "user_nodes") (Join-Path $pkg "user_nodes") -Recurse
}
# 应用资源
Copy-Item (Join-Path $root "static") (Join-Path $pkg "static") -Recurse
Copy-Item (Join-Path $root "graphs") (Join-Path $pkg "graphs") -Recurse
Copy-Item (Join-Path $root "readme.md") $pkg
New-Item -ItemType Directory -Path (Join-Path $pkg "logs") | Out-Null

# 启动器 + 说明
@"
@echo off
rem mf_server 便携版启动(无需 Python/VS 环境)
cd /d "%~dp0"
start "" /b mf_server.exe --root . --port 8001 --particles 20000 --graph graphs\default_graph.json
powershell -NoProfile -Command "$r=$null; for($i=0;$i -lt 60;$i++){ try{ $r=Invoke-WebRequest 'http://127.0.0.1:8001/api/graph' -TimeoutSec 2 -UseBasicParsing; if($r.StatusCode -eq 200){break} }catch{}; Start-Sleep 1 }; Start-Process 'http://127.0.0.1:8001/'"
"@ | Set-Content -Path (Join-Path $pkg "启动.bat") -Encoding Default

@"
mf_server 便携版 $Version
=========================
双击 启动.bat 即用(自动开浏览器 http://127.0.0.1:8001)。

内容:mf_server.exe(Release)+ 嵌入式 Python 3.14 运行时 + 站点包
(numpy/geopack)+ static/graphs 资源 + 默认图。
目标机器要求:仅 Windows 10/11 x64(无需安装 Python/VS;VC 运行库已随包)。
停止:任务管理器结束 mf_server,或 PowerShell: Get-Process mf_server | Stop-Process
日志:logs\server.jsonl
"@ | Set-Content -Path (Join-Path $pkg "使用说明.txt") -Encoding Default
Ok "便携目录就绪: $pkg"

# ---------- 4. 压缩 ----------
Info "压缩 zip"
$zip = Join-Path $root "dist\mf_server_$($Version)_win64_portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $pkg -DestinationPath $zip
$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Ok "打包完成: $zip($size MB)"
