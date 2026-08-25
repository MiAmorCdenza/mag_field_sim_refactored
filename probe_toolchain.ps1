$ErrorActionPreference = 'SilentlyContinue'
function Probe([string]$name, [scriptblock]$expr) {
  $out = & $expr 2>&1 | Select-Object -First 1
  Write-Output ("[{0}] {1}" -f $name, ($out -join ' '))
}
Probe 'cmake     ' { cmake --version }
Probe 'git       ' { git --version }
Probe 'node      ' { node --version }
Probe 'npm       ' { npm --version }
Probe 'gfortran  ' { gfortran --version }
Probe 'curl      ' { curl --version }
Probe 'system-py ' { python --version }
Probe 'venv-pip  ' { .venv\Scripts\pip --version }
Probe 'f2py      ' { python_embed\python.exe -c "import numpy.f2py; print('f2py ok')" }
Probe 'requests  ' { python_embed\python.exe -c "import requests; print('requests', requests.__version__)" }
Probe 'geopack   ' { python_embed\python.exe -c "import geopack; print('geopack import ok')" }
$vsPath = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$vs = & $vsPath -latest -property catalog_productDisplayVersion 2>$null
Write-Output ('[msvc/VS   ] ' + ($vs -join ' '))
Write-Output ('[net:github] ' + (Test-NetConnection github.com -Port 443 -WarningAction SilentlyContinue).TcpTestSucceeded)
Write-Output ('[net:pypi  ] ' + (Test-NetConnection pypi.org -Port 443 -WarningAction SilentlyContinue).TcpTestSucceeded)
