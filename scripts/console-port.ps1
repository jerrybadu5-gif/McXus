# Picks a free local port for the staff console and saves it in .env (docker compose reads MCXUS_ADMIN_PORT from it).
# Windows reserves blocks of ports for Hyper-V/WSL (see: netsh interface ipv4 show excludedportrange protocol=tcp),
# and other programs may already use 8080, so the console moves to the first port that is free.
# Use: . .\scripts\console-port.ps1 ; $port = Get-ConsolePort
function Test-PortFree([int]$Port) {
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start(); $listener.Stop(); return $true
    } catch { return $false }
}

function Get-ConsolePort {
    $root = Split-Path $PSScriptRoot -Parent
    $envFile = Join-Path $root ".env"
    $saved = $null
    if (Test-Path $envFile) {
        $line = Get-Content $envFile | Where-Object { $_ -match '^MCXUS_ADMIN_PORT=(\d+)$' } | Select-Object -First 1
        if ($line) { $saved = [int]($line -replace '^MCXUS_ADMIN_PORT=', '') }
    }
    # Already running? Keep the port it has. (Windows PowerShell treats docker's stderr as an error under
    # ErrorActionPreference=Stop, so relax it just for this call.)
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { $running = "$(& docker compose -f (Join-Path $root "docker-compose.yml") port admin 8080 2>$null)" } catch { $running = "" }
    $ErrorActionPreference = $old
    if ($running -match ':(\d+)\s*$') { $env:MCXUS_ADMIN_PORT = $Matches[1]; return [int]$Matches[1] }

    $candidates = @()
    if ($saved) { $candidates += $saved }
    $candidates += 8080, 8090, 8180, 8280, 8380, 9080, 9180, 18080, 28080, 38080
    foreach ($port in $candidates) {
        if (Test-PortFree $port) {
            if ($port -ne $saved) {
                $lines = @()
                if (Test-Path $envFile) { $lines = @(Get-Content $envFile | Where-Object { $_ -notmatch '^MCXUS_ADMIN_PORT=' }) }
                $lines += "MCXUS_ADMIN_PORT=$port"
                Set-Content -Path $envFile -Value $lines -Encoding ascii
                if ($port -ne 8080) { Write-Host "     Port 8080 is not available on this PC; the staff console uses port $port." -ForegroundColor Yellow }
            }
            $env:MCXUS_ADMIN_PORT = "$port"
            return $port
        }
    }
    throw "No free port found for the staff console. Close the program using port 8080, or put MCXUS_ADMIN_PORT=<port> in .env."
}
