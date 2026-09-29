# Maintainer-only build: end users receive the resulting setup EXE.
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
function Check-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE). See the build log." }
}
New-Item -ItemType Directory -Force artifacts | Out-Null
Start-Transcript -Path artifacts\windows-build.log -Force
try {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $compiler) { throw 'Install Inno Setup 6 on this build machine, then retry. Both per-user and machine-wide installs are supported.' }
    & py -3.11 -m venv .venv
    Check-Exit 'Creating build environment'
    $python = '.\.venv\Scripts\python.exe'
    & $python -m pip install -r packaging\requirements-build.txt
    Check-Exit 'Installing build dependencies'
    & $python -B -m unittest discover -s tests -v
    Check-Exit 'Unit tests'
    & $python scripts\smoke_first_run.py
    Check-Exit 'First-run GUI tests'
    & $python scripts\build_bundle.py
    Check-Exit 'Bundling application'
    & $compiler packaging\windows\installer.iss
    Check-Exit 'Compiling installer'
    Write-Host 'Ready: artifacts\ntp-monitor-1.1.0-windows-x64-setup.exe'
    Invoke-Item (Resolve-Path artifacts)
} catch {
    Write-Host $_ -ForegroundColor Red
    exit 1
} finally {
    Stop-Transcript
}
