# 编译 A2000 抛物面模型 DLL(标准双精度 IRBEM 源码 + 两段式 C 包装)。
# 需要 64 位 gfortran(PATH 里的 mingw32 是 32 位,配不了 64 位 Python;脚本自动探测)。
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$models = Join-Path $root "models"
$cands = @("C:\utils\mingw64\mingw64\bin\gfortran.exe", "C:\msys64\mingw64\bin\gfortran.exe",
           "C:\tools\mingw64\bin\gfortran.exe", (Get-Command gfortran -ErrorAction SilentlyContinue).Source)
$gf = $null
foreach ($c in $cands) {
  if ($c -and (Test-Path $c)) {
    $t = (& $c -dumpmachine 2>&1 | Select-Object -First 1)
    if ($t -like "x86_64*") { $gf = $c; break }
  }
}
if (-not $gf) { Write-Host "FAIL: 未找到 64 位 gfortran(-dumpmachine 需为 x86_64-*)" -ForegroundColor Red; exit 1 }
Write-Host "==> 用 $gf" -ForegroundColor Cyan
& $gf -shared -O2 -std=legacy -fdefault-real-8 -fdefault-double-8 `
      -o (Join-Path $models "a2000.dll") `
      (Join-Path $models "a2000_irbem.f") (Join-Path $models "a2000_api.f90")
if ($LASTEXITCODE -ne 0) { Write-Host "FAIL: 编译失败" -ForegroundColor Red; exit 1 }
foreach ($d in @("libgfortran-5.dll","libgcc_s_seh-1.dll","libquadmath-0.dll","libwinpthread-1.dll")) {
  $src = Join-Path (Split-Path -Parent $gf) $d
  if (Test-Path $src) { Copy-Item $src $models -Force }
}
Write-Host ("  ok: a2000.dll " + [math]::Round((Get-Item (Join-Path $models "a2000.dll")).Length/1KB,1) + " KB(运行库已随)") -ForegroundColor Green