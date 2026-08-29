# 环境依赖检查:一次性审计 C++/Python/前端工具链。
# 用法: powershell -ExecutionPolicy Bypass -File scripts\check_env.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$ok = 0
$warn = 0
$fail = 0

function Check($name, $cond, $detail) {
    if ($cond) {
        Write-Host "  [OK]   $name  $detail" -ForegroundColor Green
        $script:ok++
    } else {
        Write-Host "  [FAIL] $name  $detail" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "`n== Python(引擎/烘焙/测试)==`n" -ForegroundColor Cyan
$venvPy = Join-Path $root ".venv\Scripts\python.exe"
$basePy = "C:\Users\Admin\AppData\Local\Programs\Python\Python314\python.exe"
$pyCmd = if (Test-Path $venvPy) { $venvPy } elseif (Test-Path $basePy) { $basePy } else { $null }
if ($pyCmd) {
    $ver = & $pyCmd --version 2>&1
    Check "Python 解释器" ($LASTEXITCODE -eq 0) "($ver)"
    if (Test-Path $venvPy) {
        $pkgs = & $venvPy -m pip list 2>$null
        foreach ($p in @("numpy", "geopack", "websockets", "requests")) {
            $line = $pkgs | Select-String -Pattern "^$p\s"
            Check "venv 包 $p" ($null -ne $line) (($line -replace "\s+", " ") )
        }
    } else {
        Check "venv(.venv)" $false "缺失 —— 运行 scripts\start.ps1 自动创建"
    }
} else {
    Check "Python 解释器" $false "未找到 Python314"
}

Write-Host "`n== C++ 工具链(服务器)==`n" -ForegroundColor Cyan
$cmake = cmake --version 2>$null
Check "CMake" ($LASTEXITCODE -eq 0) ($cmake[0])
$vcvars = "C:\Program Files\Microsoft Visual Studio\18\Insiders\VC\Auxiliary\Build\vcvars64.bat"
Check "MSVC vcvars64(VS18)" (Test-Path $vcvars) $vcvars
$cache = Join-Path $root "server\build\CMakeCache.txt"
if (Test-Path $cache) {
    $c = Get-Content $cache
    $ninja = ($c | Select-String "^CMAKE_MAKE_PROGRAM:FILEPATH").Line -replace "^.*=", ""
    $pyPin = ($c | Select-String "^Python3_EXECUTABLE").Line -replace "^.*=", ""
    $btype = ($c | Select-String "^CMAKE_BUILD_TYPE").Line -replace "^.*=", ""
    Check "Ninja(生成器)" (Test-Path $ninja) $ninja
    Check "Python3_EXECUTABLE 钉死" ($pyPin -like "*Python314*") $pyPin
    Write-Host "  [info] CMAKE_BUILD_TYPE = $btype(建议 Release 跑演示)"
} else {
    Check "CMake 缓存" $false "server\build 未配置 —— start.ps1 会自动配置"
}
$exe = Join-Path $root "server\build\mf_server.exe"
Check "mf_server.exe" (Test-Path $exe) $(if (Test-Path $exe) { (Get-Item $exe).LastWriteTime } else { "" })

Write-Host "`n== 前端/辅助==`n" -ForegroundColor Cyan
$node = node --version 2>$null
Check "Node(JS 语法检查)" ($LASTEXITCODE -eq 0) $node
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe" }
Check "浏览器(Edge)" (Test-Path $edge) $edge

Write-Host "`n== 运行时状态==`n" -ForegroundColor Cyan
$srv = Get-Process mf_server -ErrorAction SilentlyContinue
if ($srv) {
    Write-Host "  [info] mf_server 已在运行(PID $($srv.Id -join ','))"
    $l = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue
    Write-Host "  [info] 端口 8001 监听: $(if ($l) { '是' } else { '否' })"
} else {
    Write-Host "  [info] mf_server 未运行"
}

Write-Host "`n结果: OK=$ok FAIL=$fail`n" -ForegroundColor $(if ($fail -eq 0) { "Green" } else { "Yellow" })
exit $(if ($fail -eq 0) { 0 } else { 1 })
