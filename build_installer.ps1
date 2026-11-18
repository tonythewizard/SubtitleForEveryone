#requires -Version 5.1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path 'dist\SubtitleForEveryone\SubtitleForEveryone.exe')) {
    throw 'Prima compila con build_windows.ps1.'
}
$found = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$compiler = if ($found) { $found.Source } else {
    @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe')
    ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $compiler) {
    throw 'Inno Setup 6 non trovato. Installa Inno Setup e ripeti.'
}
$version = (Get-Content VERSION -Raw).Trim()
$licenses = 'dist\SubtitleForEveryone\_internal\licenses'
New-Item -ItemType Directory -Path $licenses -Force | Out-Null
Copy-Item -LiteralPath 'third_party\whisper.cpp-LICENSE' -Destination $licenses
& $compiler "/DMyAppVersion=$version" (Join-Path $PSScriptRoot 'SubtitleForEveryone.iss')
if ($LASTEXITCODE -ne 0) { throw 'Errore compilazione installer.' }
Write-Host 'Installer pronto nella cartella installer\' -ForegroundColor Green
