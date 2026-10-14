# Starts McXus core (sandbox) with Docker Desktop and seeds demo users.
# Right-click > "Run with PowerShell", or in PowerShell:  .\start-dev.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker Desktop is not installed. Install it from https://www.docker.com/products/docker-desktop/ and start it." -ForegroundColor Red
    Read-Host "Press Enter to close"; exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running. Start it, wait for 'Engine running', then run this script again." -ForegroundColor Red
    Read-Host "Press Enter to close"; exit 1
}

Write-Host "1/3  Building and starting database, API and worker (first run takes a few minutes)..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "Could not start the containers." -ForegroundColor Red; Read-Host "Press Enter"; exit 1 }

Write-Host "2/3  Waiting for the API..." -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try { if ((Invoke-RestMethod http://localhost:8000/health).status -eq "ok") { $ok = $true; break } } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ok) { Write-Host "API did not start. See: docker compose logs api" -ForegroundColor Red; Read-Host "Press Enter"; exit 1 }

Write-Host "3/3  Creating demo users..." -ForegroundColor Cyan
docker compose exec -T api python -m app.cli seed-demo

Write-Host ""
Write-Host "McXus core is running (SANDBOX - test Stars only)." -ForegroundColor Green
Write-Host "  API docs:   http://localhost:8000/docs"
Write-Host "  Token:      docker compose exec api python -m app.cli dev-token 70000001"
Write-Host "  SMS codes:  docker compose logs -f api"
Write-Host "  Smoke test: python scripts\smoke_test.py"
Write-Host "  Stop:       docker compose down        (add -v to also wipe the database)"
Start-Process "http://localhost:8000/docs"
