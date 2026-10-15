# Starts the staff console (if needed) on a free port and opens it in the browser.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
. "$PSScriptRoot\console-port.ps1"
$port = Get-ConsolePort
docker compose up -d admin
if ($LASTEXITCODE -ne 0) { Write-Host "Could not start the staff console. Run the task 'McXus: start backend' first." -ForegroundColor Red; exit 1 }
Write-Host "Staff console: http://localhost:$port" -ForegroundColor Green
Start-Process "http://localhost:$port"
