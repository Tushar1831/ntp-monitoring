param(
    [Parameter(Mandatory=$true)][ValidateSet('Install','Stop','Remove')][string]$Action,
    [string]$InstallDirectory
)
$ErrorActionPreference = 'Stop'
$data = Join-Path $env:ProgramData 'NTPClientMonitor'
New-Item -ItemType Directory -Path $data -Force | Out-Null
$log = Join-Path $data 'installer.log'
try {
$name = 'NTPClientMonitor'
$service = Get-Service -Name $name -ErrorAction SilentlyContinue
if ($service -and $service.Status -ne 'Stopped') {
    Stop-Service -Name $name -ErrorAction Stop
    $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(45))
}
if ($Action -eq 'Stop') { exit 0 }
if ($Action -eq 'Remove') {
    if ($service) {
        & sc.exe delete $name
        if ($LASTEXITCODE -ne 0) { throw 'Service deletion failed' }
    }
    exit 0
}
$exe = Join-Path $InstallDirectory 'service\ntp-monitor-service.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw "Missing service executable: $exe" }
# These local data files are writable only by SYSTEM and administrators.
. (Join-Path $PSScriptRoot 'data-permissions.ps1')
Set-MonitorDataPermissions -Path $data
$binary = '"' + $exe + '"'
if ($service) {
    $existing = Get-CimInstance Win32_Service -Filter "Name='NTPClientMonitor'"
    $changed = Invoke-CimMethod -InputObject $existing -MethodName Change -Arguments @{PathName=$binary; StartMode='Manual'}
    if ($changed.ReturnValue -ne 0) { throw 'Service configuration failed' }
} else {
    New-Service -Name $name -BinaryPathName $binary -DisplayName 'NTP Client Monitor Service' -StartupType Manual | Out-Null
}
& sc.exe failure $name reset= 86400 actions= restart/10000/restart/30000/restart/60000
if ($LASTEXITCODE -ne 0) { throw 'Service recovery configuration failed' }
& sc.exe failureflag $name 1
if ($LASTEXITCODE -ne 0) { throw 'Service failure flag configuration failed' }
# Validation is captured for the GUI, not shown as a generic fatal installer error.
$cli = Join-Path $InstallDirectory 'cli\ntp-monitor.exe'
# Windows PowerShell turns native stderr into ErrorRecords: capture it without
# throwing before we can inspect the process exit code.
$ErrorActionPreference = 'Continue'
$output = & $cli --check-config --require-setup 2>&1
$validationExit = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
$output | Out-String | Set-Content -Path $log -Encoding UTF8
if ($validationExit -ne 0) {
    Add-Content -Path $log -Value 'Open NTP Client Monitor to review settings and choose Save and start.'
    exit 0
}
Set-Service -Name $name -StartupType Automatic
Start-Service -Name $name
(Get-Service $name).WaitForStatus('Running', [TimeSpan]::FromSeconds(45))
Start-Sleep -Seconds 2
if ((Get-Service $name).Status -ne 'Running') { throw 'Service exited during startup; check the Application event log' }

} catch {
    $_ | Out-String | Set-Content -Path $log -Encoding UTF8
    exit 1
}
