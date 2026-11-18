#requires -Version 7.0
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or -not $env:RUNNER_TEMP) {
    throw 'Use this script on a disposable GitHub Actions runner.'
}
$project = Split-Path -Parent $PSScriptRoot
$version = (Get-Content (Join-Path $project 'VERSION') -Raw).Trim()
$setup = Join-Path $project "installer\SubtitleForEveryone-Setup-$version-x64.exe"
$target = Join-Path $env:RUNNER_TEMP 'SubtitleForEveryone-smoke'
$options = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=desktopicon', ('/DIR="' + $target + '"'))
$installer = Start-Process -FilePath $setup -ArgumentList $options -Wait -PassThru -WindowStyle Hidden
if ($installer.ExitCode -ne 0) { throw "Setup exited with $($installer.ExitCode)." }
$exe = Join-Path $target 'SubtitleForEveryone.exe'
$registration = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{6BCA5755-0E2B-4E15-8B2C-1557B721000A}_is1'
if ($registration.DisplayVersion -ne $version) { throw 'Unexpected installer version.' }
$shortcuts = New-Object -ComObject WScript.Shell
foreach ($folder in 'DesktopDirectory','Programs') {
    $shortcut = Join-Path ([Environment]::GetFolderPath($folder)) 'SubtitleForEveryone.lnk'
    if (-not (Test-Path $shortcut) -or $shortcuts.CreateShortcut($shortcut).TargetPath -ne $exe) {
        throw "Missing or invalid shortcut in $folder."
    }
}
$result = Join-Path $env:RUNNER_TEMP 'SubtitleForEveryone-self-test.json'
$env:PATH = "$env:WINDIR\System32;$env:WINDIR"
$test = Start-Process -FilePath $exe -ArgumentList @('--self-test', ('"' + $result + '"')) -PassThru -WindowStyle Hidden
if (-not $test.WaitForExit(120000)) {
    Stop-Process -Id $test.Id
    throw 'Installed runtime test timed out.'
}
if (-not (Test-Path $result)) { throw 'Installed executable did not write its test result.' }
$contents = Get-Content $result -Raw
if ($test.ExitCode -ne 0) { throw $contents }
$check = $contents | ConvertFrom-Json
if ($check.status -ne 'ok' -or $check.version -ne $version) { throw $contents }
Write-Host "Installed SubtitleForEveryone $version and verified its bundled runtime."
