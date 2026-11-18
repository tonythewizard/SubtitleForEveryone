#requires -Version 5.1
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup_windows.ps1 first.' }
& $python -c 'import PyInstaller'
if ($LASTEXITCODE -ne 0) { throw 'Install the dependencies in requirements-build.txt.' }

$native = Join-Path $PSScriptRoot 'build\package-native'
& (Join-Path $PSScriptRoot 'build_audio_helper.ps1') -WithVulkan -OutputDirectory $native
$vulkanPackage = Join-Path $PSScriptRoot 'build\package-vulkan'
$previousVulkan = $env:SUBTITLEFOREVERYONE_VULKAN_DIR
try {
    $env:SUBTITLEFOREVERYONE_VULKAN_DIR = $vulkanPackage
    & (Join-Path $PSScriptRoot 'setup_vulkan.ps1') -BuildOnly
} finally {
    $env:SUBTITLEFOREVERYONE_VULKAN_DIR = $previousVulkan
}
$server = Join-Path $vulkanPackage 'whisper-server.exe'
if (-not (Test-Path -LiteralPath $server)) { throw 'The Vulkan server was not built.' }
& $python -m tools.build_icon
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }

$pack = @('--noconfirm','--clean','--onedir','--windowed',
          '--name','SubtitleForEveryone',
          '--icon','build/SubtitleForEveryone.ico',
          '--add-binary',"$native\app_audio.exe;build/native",
          '--add-binary',"$native\vulkan_devices.exe;whisper-vulkan",
          '--add-binary',"$server;whisper-vulkan",
          '--add-data','app/ui_strings.txt;app',
          '--add-data','VERSION;.',
          '--add-data','LICENSE;.',
          '--collect-all','faster_whisper',
          '--collect-all','ctranslate2',
          '--collect-all','proctap',
          '--collect-all','argostranslate',
          '--collect-data','minisbd',
          '--exclude-module','nvidia',
          '--copy-metadata','huggingface-hub',
          'launch.py')
& $python -m PyInstaller @pack
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

# App-local Visual C++ runtime for Windows PCs without the development tools.
$crt = Get-ChildItem -Path "$env:VCToolsRedistDir\x64\Microsoft.VC*.CRT" -Directory |
    Select-Object -First 1
if (-not $crt) { throw 'Visual C++ redistributable files not found.' }
Copy-Item -Path (Join-Path $crt.FullName '*.dll') -Destination 'dist\SubtitleForEveryone\_internal'

# Keep the dependency license files so this bundle carries their notices.
& $python -m tools.collect_notices
if ($LASTEXITCODE -ne 0) { throw 'Failed to collect dependency notices.' }
# The archive already contains the wheel notices. Removing the duplicate
# copies from the generated bundle avoids Windows path-length limits.
$internal = (Resolve-Path -LiteralPath 'dist\SubtitleForEveryone\_internal').Path
foreach ($metadata in Get-ChildItem -LiteralPath $internal -Directory -Filter '*.dist-info') {
    $wheelNotices = Join-Path $metadata.FullName 'licenses'
    if (Test-Path -LiteralPath $wheelNotices) {
        $resolved = (Resolve-Path -LiteralPath $wheelNotices).Path
        if (-not $resolved.StartsWith($internal + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Unexpected wheel license path outside the generated package.'
        }
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
