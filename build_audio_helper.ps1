#requires -Version 5.1
$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Installa Visual Studio Build Tools con Desktop development with C++.' }
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Compilatore MSVC x64 non trovato.' }
Import-Module (Join-Path $vs 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
$output = Join-Path $PSScriptRoot 'build\native'
New-Item -ItemType Directory -Path $output -Force | Out-Null
$source = Join-Path $PSScriptRoot 'native\app_audio.cpp'
& cl.exe /nologo /O2 /EHsc /MT /std:c++17 "/Fo$output\app_audio.obj" "/Fe$output\app_audio.exe" $source Ole32.lib Mmdevapi.lib
if ($LASTEXITCODE -ne 0) { throw 'Compilazione della cattura WASAPI non riuscita.' }
