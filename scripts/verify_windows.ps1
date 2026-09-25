# Disposable elevated Windows VM only. Does not change the system clock.
param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [switch]$AllowExistingPython
)
$ErrorActionPreference = 'Stop'
if (-not $AllowExistingPython) {
    if ((Get-Command python.exe -ErrorAction SilentlyContinue) -or (Get-Command python3.exe -ErrorAction SilentlyContinue)) {
        throw 'Use a clean VM without Python (disable Windows Python execution aliases too)'
    }
}
$data = Join-Path $env:ProgramData 'NTPClientMonitor'
if (Test-Path "$data\config.json") { throw 'Expected a fresh VM with no application data' }
New-Item -ItemType Directory -Path $data -Force | Out-Null
@{primary_server='127.0.0.1'; timeout_seconds=0.1; log_directory='./logs'; sync_system_clock=$false; workstation_name='package-test'} |
    ConvertTo-Json | Set-Content "$data\config.json" -Encoding Ascii
function Install-Package {
    $process = Start-Process -FilePath $Installer -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-' -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer exit code $($process.ExitCode)" }
}
function Assert-Running {
    if ((Get-Service NTPClientMonitor).Status -ne 'Running') { throw 'Service is not running' }
}
Install-Package
Assert-Running
if ((Get-CimInstance Win32_Service -Filter "Name='NTPClientMonitor'").StartMode -ne 'Auto') { throw 'Not configured for boot startup' }
for ($i=0; $i -lt 30 -and -not (Test-Path "$data\logs\package-test_ntpstatus.xml"); $i++) { Start-Sleep 1 }
[xml]$status = Get-Content "$data\logs\package-test_ntpstatus.xml"
if ($status.NTPClientStatus.SyncReason -ne 'no_usable_server') { throw 'Expected offline test snapshot' }
$before = (Get-FileHash "$data\config.json").Hash
$serviceProcess = (Get-CimInstance Win32_Service -Filter "Name='NTPClientMonitor'").ProcessId
Stop-Process -Id $serviceProcess -Force
Start-Sleep 15
Assert-Running
$newProcess = (Get-CimInstance Win32_Service -Filter "Name='NTPClientMonitor'").ProcessId
if ($newProcess -eq $serviceProcess) { throw 'Service did not restart' }
Install-Package
if ((Get-FileHash "$data\config.json").Hash -ne $before) { throw 'Reinstall overwrote configuration' }
Assert-Running
$uninstaller = Join-Path $env:ProgramFiles 'NTP Client Monitor\unins000.exe'
$process = Start-Process -FilePath $uninstaller -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Uninstall failed' }
if (Get-Service NTPClientMonitor -ErrorAction SilentlyContinue) { throw 'Service registration survived uninstall' }
if (-not (Test-Path "$data\config.json")) { throw 'Uninstall deleted configuration' }
if (-not (Test-Path "$data\logs\package-test_ntplog.xml")) { throw 'Uninstall deleted logs' }
Write-Output 'Install, startup, crash recovery, reinstall preservation and uninstall verified'
