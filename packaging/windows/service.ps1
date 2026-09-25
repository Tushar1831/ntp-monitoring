param(
    [Parameter(Mandatory=$true)][ValidateSet('Install','Stop','Remove')][string]$Action,
    [string]$InstallDirectory
)
$ErrorActionPreference = 'Stop'
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
$data = Join-Path $env:ProgramData 'NTPClientMonitor'
# These local data files are writable only by SYSTEM and administrators.
& icacls.exe $data /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /T
if ($LASTEXITCODE -ne 0) { throw 'Failed to secure application data' }
$binary = '"' + $exe + '"'
if ($service) {
    $existing = Get-CimInstance Win32_Service -Filter "Name='NTPClientMonitor'"
    $changed = Invoke-CimMethod -InputObject $existing -MethodName Change -Arguments @{PathName=$binary; StartMode='Automatic'}
    if ($changed.ReturnValue -ne 0) { throw 'Service configuration failed' }
} else {
    New-Service -Name $name -BinaryPathName $binary -DisplayName 'NTP Client Monitor Service' -StartupType Automatic | Out-Null
}
& sc.exe failure $name reset= 86400 actions= restart/10000/restart/30000/restart/60000
if ($LASTEXITCODE -ne 0) { throw 'Service recovery configuration failed' }
& sc.exe failureflag $name 1
if ($LASTEXITCODE -ne 0) { throw 'Service failure flag configuration failed' }
Start-Service -Name $name
(Get-Service $name).WaitForStatus('Running', [TimeSpan]::FromSeconds(45))
Start-Sleep -Seconds 2
if ((Get-Service $name).Status -ne 'Running') { throw 'Service exited during startup; check the Application event log' }
