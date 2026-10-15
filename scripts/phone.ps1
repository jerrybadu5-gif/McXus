# McXus Android helper for a phone on USB (developer options + USB debugging on).
# Used by the VS Code tasks (Terminal > Run Task...), or directly in PowerShell from the McXus folder:
#   .\scripts\phone.ps1 check      is the phone connected and authorised?
#   .\scripts\phone.ps1 build      build the debug APK
#   .\scripts\phone.ps1 install    build, install and open McXus on the phone (server reachable over USB)
#   .\scripts\phone.ps1 test       smoke test ON the phone (+ a real encrypted chat if the backend is running)
#   .\scripts\phone.ps1 log        live app log from the phone (Ctrl+C to stop)
#   .\scripts\phone.ps1 reverse    let the phone reach the laptop's server at http://127.0.0.1:8000 over USB
# Several devices (e.g. your phone + the PC emulator)? By default every connected device is used.
# Pick one with  -Device phone  |  -Device emulator  |  -Device <serial from 'adb devices'>
param(
    [ValidateSet("check", "build", "install", "test", "log", "reverse")] [string]$Action = "check",
    [string]$Server = "usb",
    [string]$Device = "all"
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$android = Join-Path $root "android"

function Fail($msg) { Write-Host $msg -ForegroundColor Red; exit 1 }

function Find-Sdk {
    $props = Join-Path $android "local.properties"
    if (Test-Path $props) {
        $line = Get-Content $props | Where-Object { $_ -match '^sdk\.dir=' } | Select-Object -First 1
        if ($line) { return ($line -replace '^sdk\.dir=', '' -replace '\\\\', '\' -replace '\\:', ':') }
    }
    foreach ($c in @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, "$env:LOCALAPPDATA\Android\Sdk")) { if ($c -and (Test-Path $c)) { return $c } }
    Fail "Android SDK not found. Run:  .\scripts\setup-android-windows.ps1"
}

function Use-Java {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) { return }
    $candidates = @("$env:ProgramFiles\Android\Android Studio\jbr") + (Get-ChildItem "$env:ProgramFiles\Microsoft\jdk-17*" -ErrorAction SilentlyContinue | ForEach-Object FullName)
    foreach ($c in $candidates) { if ($c -and (Test-Path "$c\bin\java.exe")) { $env:JAVA_HOME = $c; return } }
    Fail "Java 17 not found. Run:  .\scripts\setup-android-windows.ps1"
}

$sdk = Find-Sdk
$adb = Join-Path $sdk "platform-tools\adb.exe"
if (-not (Test-Path $adb)) { Fail "adb not found in $sdk\platform-tools. Run:  .\scripts\setup-android-windows.ps1" }

function Gradle([string[]]$tasks) {
    Use-Java
    Push-Location $android
    try {
        & .\gradlew.bat @tasks
        if ($LASTEXITCODE -ne 0) { Fail "Gradle failed: $($tasks -join ' ')" }
    } finally { Pop-Location }
}

function Get-Devices {
    $lines = & $adb devices | Select-Object -Skip 1 | Where-Object { $_.Trim() -ne "" }
    if ($lines -match "unauthorized") { Write-Host "A device is not authorised: unlock it and tap 'Allow USB debugging' (tick 'Always allow')." -ForegroundColor Yellow }
    foreach ($line in $lines) {
        $parts = $line -split "\s+"
        if ($parts[1] -eq "device") {
            $serial = $parts[0]
            [pscustomobject]@{
                Serial   = $serial
                Emulator = $serial -like "emulator-*"
                Model    = (& $adb -s $serial shell getprop ro.product.model).Trim()
            }
        }
    }
}

# The devices this run works on. With exactly one, ANDROID_SERIAL makes Gradle and adb use only that one.
function Require-Phone {
    $all = @(Get-Devices)
    if ($all.Count -eq 0) {
        Fail ("No phone found. Check: 1) USB cable supports data  2) Settings > Developer options > USB debugging ON  " +
            "3) pull down the notification and choose USB mode 'File transfer'  4) unlock the phone and allow this computer.")
    }
    $picked = switch ($Device) {
        "all" { $all }
        "phone" { @($all | Where-Object { -not $_.Emulator } | Select-Object -First 1) }
        "emulator" { @($all | Where-Object { $_.Emulator } | Select-Object -First 1) }
        default { @($all | Where-Object { $_.Serial -eq $Device }) }
    }
    $picked = @($picked | Where-Object { $_ })
    if ($picked.Count -eq 0) { Fail "No device matches -Device $Device. Connected: $(($all | ForEach-Object { "$($_.Model) ($($_.Serial))" }) -join ', ')" }
    if ($picked.Count -eq 1) { $env:ANDROID_SERIAL = $picked[0].Serial } else { Remove-Item Env:ANDROID_SERIAL -ErrorAction SilentlyContinue }
    Write-Host ("Using: " + (($picked | ForEach-Object { "$($_.Model) ($($_.Serial))" }) -join ", ")) -ForegroundColor Cyan
    return $picked
}

function Server-Up { try { return (Invoke-RestMethod http://localhost:8000/health -TimeoutSec 3).status -eq "ok" } catch { return $false } }

function Reverse($devices) {
    foreach ($d in $devices) { & $adb -s $d.Serial reverse tcp:8000 tcp:8000 | Out-Null }
    Write-Host "USB link ready: in McXus set Server to  http://127.0.0.1:8000  (works without Wi-Fi while the cable is in)." -ForegroundColor Green
}

switch ($Action) {
    "check" {
        foreach ($d in (Require-Phone)) {
            $version = (& $adb -s $d.Serial shell getprop ro.build.version.release).Trim()
            $abi = (& $adb -s $d.Serial shell getprop ro.product.cpu.abi).Trim()
            $kind = if ($d.Emulator) { "emulator" } else { "phone" }
            Write-Host "Connected $kind`: $($d.Model), Android $version, CPU $abi  (serial $($d.Serial))" -ForegroundColor Green
            if ([int]($version.Split('.')[0]) -lt 8) { Write-Host "  McXus needs Android 8 or newer." -ForegroundColor Red }
        }
        if (Server-Up) { Write-Host "Backend is running on this laptop." -ForegroundColor Green } else { Write-Host "Backend not running yet: run task 'McXus: start backend'." -ForegroundColor Yellow }
    }
    "build" {
        Gradle @("assembleDebug")
        Write-Host "APK: $android\app\build\outputs\apk\debug\app-debug.apk" -ForegroundColor Green
    }
    "reverse" { Reverse (Require-Phone) }
    "install" {
        $devices = Require-Phone
        Gradle @("installDebug")
        Reverse $devices
        foreach ($d in $devices) { & $adb -s $d.Serial shell am start -n pg.mcxus.app/.MainActivity | Out-Null }
        Write-Host "McXus is open on: $(($devices | ForEach-Object Model) -join ', ')." -ForegroundColor Green
    }
    "test" {
        $devices = Require-Phone
        $gradleArgs = @("connectedDebugAndroidTest")
        if ($Server -eq "usb") {
            if (Server-Up) { Reverse $devices; $Server = "http://127.0.0.1:8000" } else { $Server = ""; Write-Host "Backend not running: skipping the server chat test (start it to include it)." -ForegroundColor Yellow }
        }
        if ($Server) { $gradleArgs += "-Pandroid.testInstrumentationRunnerArguments.server=$Server" }
        Gradle $gradleArgs
        Write-Host "Phone smoke test PASSED. Report: $android\app\build\reports\androidTests\connected\debug\index.html" -ForegroundColor Green
    }
    "log" {
        $devices = @(Require-Phone)
        # One log at a time: prefer the real phone when several are connected.
        $d = @($devices | Where-Object { -not $_.Emulator }) + @($devices | Where-Object { $_.Emulator }) | Select-Object -First 1
        if ($devices.Count -gt 1) { Write-Host "Showing $($d.Model). For another: -Device <serial>" -ForegroundColor Yellow }
        $pid_ = (& $adb -s $d.Serial shell pidof -s pg.mcxus.app).Trim()
        if (-not $pid_) { Fail "McXus is not running on $($d.Model). Open it first (task 'Android: install & open on phone')." }
        Write-Host "Live log for McXus on $($d.Model) (pid $pid_). Ctrl+C to stop." -ForegroundColor Cyan
        & $adb -s $d.Serial logcat -v time --pid=$pid_
    }
}
