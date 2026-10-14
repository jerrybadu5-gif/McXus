# Runs every check the CI runs: unit + API tests, lint, format, type check, dependency audit.
# Needs Python 3.12+ and Docker Desktop (for the test database).   .\run-tests.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($name, [scriptblock]$cmd) {
    Write-Host "`n== $name" -ForegroundColor Cyan
    & $cmd
    if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $name" -ForegroundColor Red; Read-Host "Press Enter to close"; exit 1 }
}

Step "Start test database" { docker compose up -d db }
for ($i = 0; $i -lt 30; $i++) { docker compose exec -T db pg_isready -U mcxus *> $null; if ($LASTEXITCODE -eq 0) { break }; Start-Sleep 2 }

Set-Location "$PSScriptRoot\backend"
if (-not (Test-Path ".venv")) { Step "Create Python environment" { python -m venv .venv } }
$py = ".venv\Scripts\python.exe"
Step "Install packages" { & $py -m pip install --quiet --upgrade pip; & $py -m pip install --quiet -e ".[dev]" }

$env:MCXUS_TEST_DATABASE_URL = "postgresql+psycopg://mcxus:mcxus@localhost:5433/mcxus_test"
Step "Tests" { & $py -m pytest -W ignore::DeprecationWarning }
Step "Lint (ruff)" { & $py -m ruff check . }
Step "Format check (ruff)" { & $py -m ruff format --check . }
Step "Type check (mypy)" { & $py -m mypy app }
Step "Dependency audit (pip-audit)" { & $py -m pip_audit --skip-editable }

Write-Host "`nAll checks passed." -ForegroundColor Green
Read-Host "Press Enter to close"
