# One-time setup on Windows for building the McXus Android app from VS Code (no Android Studio needed).
# Installs: Java 17 (Microsoft OpenJDK, via winget), Android command-line tools, platform-tools (adb),
# Android 15 SDK (API 35) and build-tools 35. About 1.5 GB download. Run in PowerShell from the McXus folder:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup-android-windows.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

Write-Host "1/4  Java 17" -ForegroundColor Cyan
$jdk = Get-ChildItem "$env:ProgramFiles\Microsoft\jdk-17*" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $jdk) {
    winget install --id Microsoft.OpenJDK.17 -e --accept-source-agreements --accept-package-agreements
    $jdk = Get-ChildItem "$env:ProgramFiles\Microsoft\jdk-17*" | Select-Object -First 1
}
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdk.FullName, "User")
$env:JAVA_HOME = $jdk.FullName
Write-Host "     JAVA_HOME = $($jdk.FullName)"

Write-Host "2/4  Android command-line tools" -ForegroundColor Cyan
$sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { "$env:LOCALAPPDATA\Android\Sdk" }
$tools = "$sdk\cmdline-tools\latest"
if (-not (Test-Path "$tools\bin\sdkmanager.bat")) {
    New-Item -ItemType Directory -Force "$sdk\cmdline-tools" | Out-Null
    $zip = "$env:TEMP\android-cmdline-tools.zip"
    Invoke-WebRequest "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" -OutFile $zip
    Expand-Archive $zip "$sdk\cmdline-tools\tmp" -Force
    Move-Item "$sdk\cmdline-tools\tmp\cmdline-tools" $tools -Force
    Remove-Item "$sdk\cmdline-tools\tmp" -Recurse -Force
}

Write-Host "3/4  SDK packages (accepting the Android SDK licences)" -ForegroundColor Cyan
$sdkmanager = "$tools\bin\sdkmanager.bat"
"y`ny`ny`ny`ny`ny`ny`ny`n" | & $sdkmanager --sdk_root=$sdk --licenses | Out-Null
& $sdkmanager --sdk_root=$sdk "platform-tools" "platforms;android-35" "build-tools;35.0.0"
if ($LASTEXITCODE -ne 0) { Write-Host "sdkmanager failed (check the internet connection and run again)." -ForegroundColor Red; exit 1 }
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $sdk, "User")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$sdk\platform-tools*") { [Environment]::SetEnvironmentVariable("Path", "$userPath;$sdk\platform-tools", "User") }

Write-Host "4/4  android\local.properties" -ForegroundColor Cyan
"sdk.dir=$($sdk -replace '\\', '\\' -replace ':', '\:')" | Set-Content -Encoding ASCII "$root\android\local.properties"

Write-Host ""
Write-Host "Done. Close and reopen VS Code so it sees JAVA_HOME and adb, then run the task 'Android: check phone'." -ForegroundColor Green
Write-Host "Phone: Settings > About phone > tap 'Build number' 7 times; Developer options > USB debugging ON." -ForegroundColor Yellow
