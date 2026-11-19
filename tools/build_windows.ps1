# Build and smoke-test the portable Windows executable.
#   powershell -ExecutionPolicy Bypass -File tools\build_windows.ps1 [-Python 3.12]
param([string]$Python = "3.12")
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
Set-Location (Split-Path $PSScriptRoot -Parent)

uv sync --extra dev --python $Python
if ($LASTEXITCODE) { throw 'uv sync failed' }
uv run pytest -q
if ($LASTEXITCODE) { throw 'tests failed' }
uv run python tools/make_icons.py build/icons
if ($LASTEXITCODE) { throw 'icons failed' }
uv run pyinstaller --noconfirm --clean --distpath build/pyi-dist --workpath build/pyi-work packaging/redpoint.spec
if ($LASTEXITCODE) { throw 'pyinstaller failed' }
$version = (uv run python -c "import redpoint; print(redpoint.__version__)").Trim()

# Smoke test from a folder outside the checkout, with no Python on PATH.
$smoke = Join-Path $env:TEMP "redpoint-smoke"
Remove-Item $smoke -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $smoke | Out-Null
Copy-Item build\pyi-dist\Redpoint.exe $smoke\Redpoint.exe
$oldPath = $env:PATH
$env:PATH = "$env:WINDIR\System32;$env:WINDIR"
try {
  $p = Start-Process "$smoke\Redpoint.exe" -ArgumentList '--self-test', "$smoke\out" -Wait -PassThru
} finally { $env:PATH = $oldPath }
Get-Content "$smoke\out\report.json"
if ($p.ExitCode -ne 0) { throw "self-test failed ($($p.ExitCode))" }

New-Item -ItemType Directory dist -Force | Out-Null
Copy-Item build\pyi-dist\Redpoint.exe "dist\Redpoint-$version-windows-x64.exe"
$zipDir = "build\zip\Redpoint"
Remove-Item build\zip -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $zipDir | Out-Null
Copy-Item build\pyi-dist\Redpoint.exe, LICENSE "$zipDir\"
Copy-Item packaging\README-Windows.txt "$zipDir\README.txt"
Compress-Archive -Path "$zipDir\*" -DestinationPath "dist\Redpoint-$version-windows-x64.zip" -Force
Get-ChildItem dist
