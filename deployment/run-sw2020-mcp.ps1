# Repo-local stdio launcher. Requires an already installed .venv and SW2020.
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoRoot '.venv\Scripts\python.exe'
$entryPath = Join-Path $repoRoot 'src\utils\start_sw2020_stable.py'
if (!(Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install the project first. See README_CAE.md.'
}
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
Push-Location -LiteralPath $repoRoot
try {
    & $pythonPath $entryPath --real --year 2020
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
