# Native regression test: no installed service or clock changes required.
$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Permission tests require an elevated administrator session'
}
. (Join-Path $PSScriptRoot '..\packaging\windows\data-permissions.ps1')
$root = Join-Path $env:TEMP ('ntp-acl-test-' + [guid]::NewGuid())
function Assert-DataAccess([string]$File) {
    if ((Get-Content -LiteralPath $File -Raw) -ne '{"setup_complete":false}') {
        throw 'Securing the data directory changed configuration contents'
    }
    [IO.File]::WriteAllText($File, '{"setup_complete":false}')
    $acl = Get-Acl -LiteralPath $File
    if ($acl.AreAccessRulesProtected) { throw 'Child inheritance is disabled' }
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
        if (-not ($rules | Where-Object {
            $_.IdentityReference.Value -eq $sid -and
            $_.AccessControlType -eq 'Allow' -and
            ($_.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq [Security.AccessControl.FileSystemRights]::FullControl
        })) { throw "Missing full control for $sid" }
    }
    if ($rules | Where-Object { $_.IdentityReference.Value -notin @('S-1-5-18', 'S-1-5-32-544') }) {
        throw 'Unexpected access to application data'
    }
}
try {
    New-Item -ItemType Directory -Path "$root\logs" -Force | Out-Null
    $config = Join-Path $root 'config.json'
    $nested = Join-Path $root 'logs\history.xml'
    foreach ($file in @($config, $nested)) {
        [IO.File]::WriteAllText($file, '{"setup_complete":false}')
    }
    Set-MonitorDataPermissions -Path $root
    Assert-DataAccess $config
    Assert-DataAccess $nested
    # Model a protected file left behind by an earlier installation.
    $acl = Get-Acl -LiteralPath $config
    $acl.SetAccessRuleProtection($true, $true)
    Set-Acl -LiteralPath $config -AclObject $acl
    Set-MonitorDataPermissions -Path $root
    Assert-DataAccess $config
    Assert-DataAccess $nested
    $newFile = Join-Path $root 'new.json'
    [IO.File]::WriteAllText($newFile, '{"setup_complete":false}')
    Assert-DataAccess $newFile
    Write-Output 'Configuration access, nested files, reinstall repair and new-file inheritance verified'
} finally {
    if (Test-Path -LiteralPath $root) { Remove-Item -LiteralPath $root -Recurse -Force }
}
