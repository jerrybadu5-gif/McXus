# Starts McXus core (sandbox) with Docker Desktop and seeds demo users.
# Right-click > "Run with PowerShell", or in PowerShell:  .\start-dev.ps1
# For the Android app on a phone on the same Wi-Fi:      .\start-dev.ps1 -Lan
param([switch]$Lan)
$ErrorActionPreference = "Stop"
if ($Lan) { $env:MCXUS_API_BIND = "0.0.0.0" } else { $env:MCXUS_API_BIND = "127.0.0.1" }
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

Write-Host "1/3  Building and starting database, API, worker and staff console (first run takes a few minutes)..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "Could not start the containers." -ForegroundColor Red; Read-Host "Press Enter"; exit 1 }

Write-Host "2/3  Waiting for the API..." -ForegroundColor Cyan
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    try { if ((Invoke-RestMethod http://localhost:8000/health).status -eq "ok") { $ok = $true; break } } catch {}
    Start-Sleep -Seconds 2
}
if (-not $ok) { Write-Host "API did not start. See: docker compose logs api" -ForegroundColor Red; Read-Host "Press Enter"; exit 1 }

$level = (Invoke-RestMethod http://localhost:8000/health).api_level
if (-not $level -or $level -lt 6) {
    Write-Host "The API is an old build (api_level $level). Run:  docker compose build --no-cache api worker; docker compose up -d" -ForegroundColor Red
} else { Write-Host "     Server api_level $level (matches the app)" -ForegroundColor Green }

Write-Host "3/3  Creating demo users..." -ForegroundColor Cyan
docker compose exec -T api python -m app.cli seed-demo

Write-Host ""
Write-Host "McXus core is running (SANDBOX - test Stars only)." -ForegroundColor Green
Write-Host "  Staff console: http://localhost:8080   (mediator 70000005, compliance 70000009, finance 70000003/4, admin 70000006)"
Write-Host "  Sample disputes: docker compose exec api python -m app.cli seed-disputes"
Write-Host "  API docs:   http://localhost:8000/docs"
Write-Host "  Token:      docker compose exec api python -m app.cli dev-token 70000001"
Write-Host "  SMS codes:  docker compose logs -f api"
Write-Host "  Smoke test: python scripts\smoke_test.py"
Write-Host "  Stop:       docker compose down        (add -v to also wipe the database)"
if ($Lan) {
    $ips = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notmatch '^(127|169\.254)\.' -and $_.PrefixOrigin -ne 'WellKnown' }
    Write-Host ""
    Write-Host "Phone testing (same Wi-Fi): in the McXus app, set the server to one of:" -ForegroundColor Yellow
    foreach ($ip in $ips) { Write-Host "  http://$($ip.IPAddress):8000" -ForegroundColor Yellow }
    Write-Host "  If Windows asks, allow Docker on PRIVATE networks only. Stop with: docker compose down" -ForegroundColor Yellow
}
Start-Process "http://localhost:8000/docs"
