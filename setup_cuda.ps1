#requires -Version 5.1
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Esegui prima setup_windows.ps1.' }
& $python -m pip install 'nvidia-cublas-cu12==12.9.2.10' 'nvidia-cudnn-cu12==9.28.1.4' 'nvidia-cuda-nvrtc-cu12==12.9.86'
if ($LASTEXITCODE -ne 0) { throw 'Installazione dei runtime CUDA non riuscita.' }
