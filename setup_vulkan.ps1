#requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('tiny','base','small','medium','large-v3')]
    [string]$Model = 'tiny',
    [int]$GpuIndex = -1,
    [switch]$Check,
    [switch]$BuildOnly
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$destination = if ($env:SUBTITLEFOREVERYONE_VULKAN_DIR) {
    $env:SUBTITLEFOREVERYONE_VULKAN_DIR
} else { Join-Path $PSScriptRoot 'whisper-vulkan' }
$destination = [IO.Path]::GetFullPath($destination)
$env:SUBTITLEFOREVERYONE_VULKAN_DIR = $destination

function Invoke-Checked($Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe terminato con codice $LASTEXITCODE." }
}

$sdk = $env:VULKAN_SDK
if (-not $sdk -and (Test-Path (Join-Path $PSScriptRoot 'whisper-vulkan-build\sdk\Bin\glslc.exe'))) {
    $sdk = Join-Path $PSScriptRoot 'whisper-vulkan-build\sdk'
}
if (-not $sdk -and (Test-Path 'C:\VulkanSDK')) {
    $sdk = Get-ChildItem 'C:\VulkanSDK' -Directory |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
$server = Join-Path $destination 'whisper-server.exe'
if (-not (Test-Path -LiteralPath $server)) {
    if (-not $sdk -or -not (Test-Path (Join-Path $sdk 'Bin\glslc.exe'))) {
        throw 'Vulkan SDK con glslc mancante. Installa il Vulkan SDK Windows di LunarG e riapri PowerShell.'
    }
    $env:VULKAN_SDK = $sdk
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $vswhere)) { throw 'Visual Studio Build Tools non trovato.' }
    $vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw 'Visual Studio Build Tools con strumenti C++ x64 non trovato.' }
    $tools = Join-Path $vs 'Common7\IDE\CommonExtensions\Microsoft\CMake'
    $cmake = Get-Command cmake.exe -ErrorAction SilentlyContinue
    $ninjaTool = Get-Command ninja.exe -ErrorAction SilentlyContinue
    $cmakePath = if ($cmake) { $cmake.Source } else { Join-Path $tools 'CMake\bin\cmake.exe' }
    $ninja = if ($ninjaTool) { $ninjaTool.Source } else { Join-Path $tools 'Ninja\ninja.exe' }
    if (-not (Test-Path $cmakePath) -or -not (Test-Path $ninja)) { throw 'Installa il componente CMake per C++ di Visual Studio.' }
    if ($Check) { Write-Host 'Prerequisiti di compilazione trovati.'; return }
    $source = Join-Path $PSScriptRoot 'whisper-vulkan-build\source'
    $build = Join-Path $PSScriptRoot 'vk-build'
    if (-not (Test-Path (Join-Path $source 'CMakeLists.txt'))) {
        $version = '1.8.3'
        $work = Split-Path -Parent $source
        New-Item -ItemType Directory -Path $work -Force | Out-Null
        $archive = Join-Path $work "source-v$version.zip"
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -UseBasicParsing "https://codeload.github.com/ggml-org/whisper.cpp/zip/refs/tags/v$version" -OutFile $archive
        Expand-Archive -LiteralPath $archive -DestinationPath $work -Force
        Move-Item -LiteralPath (Join-Path $work "whisper.cpp-$version") -Destination $source
    }
    Import-Module (Join-Path $vs 'Common7\Tools\Microsoft.VisualStudio.DevShell.dll')
    Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
    $env:Path = (Split-Path -Parent $ninja) + ';' + $env:Path
    Invoke-Checked $cmakePath @('-S',$source,'-B',$build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        '-DGGML_VULKAN=ON','-DGGML_NATIVE=OFF','-DWHISPER_BUILD_SERVER=ON',
        '-DWHISPER_BUILD_TESTS=OFF','-DBUILD_SHARED_LIBS=OFF')
    Invoke-Checked $cmakePath @('--build',$build,'--target','whisper-server','--parallel','4')
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $build 'bin\whisper-server.exe') -Destination $server
}

if ($Check) { Write-Host "Server trovato: $server"; return }
if ($BuildOnly) { return }
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Esegui prima setup_windows.ps1.' }
Invoke-Checked $python @('-m','app.vulkan',$Model,"$GpuIndex")
