#requires -Version 5.1
[CmdletBinding()]
param([switch]$WithVulkan, [string]$OutputDirectory = (Join-Path $PSScriptRoot 'build\native'))
$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Installa Visual Studio Build Tools con Desktop development with C++.' }
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'Compilatore MSVC x64 non trovato.' }
Import-Module (Join-Path $vs 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $output -Force | Out-Null
$source = Join-Path $PSScriptRoot 'native\app_audio.cpp'
& cl.exe /nologo /O2 /EHsc /MT /std:c++17 "/Fo$output\app_audio.obj" "/Fe$output\app_audio.exe" $source Ole32.lib Mmdevapi.lib
if ($LASTEXITCODE -ne 0) { throw 'Compilazione della cattura WASAPI non riuscita.' }
if ($WithVulkan) {
    if (-not $env:VULKAN_SDK) { throw 'Set VULKAN_SDK to the Windows Vulkan SDK.' }
    $include = Join-Path $env:VULKAN_SDK 'Include'
    $probe = Join-Path $PSScriptRoot 'native\vulkan_devices.cpp'
    & cl.exe /nologo /O2 /EHsc /MT /std:c++17 "/I$include" "/Fo$output\vulkan_devices.obj" "/Fe$output\vulkan_devices.exe" $probe
    if ($LASTEXITCODE -ne 0) { throw 'Vulkan device probe build failed.' }
}
