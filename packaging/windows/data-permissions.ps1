function Set-MonitorDataPermissions {
    param([Parameter(Mandatory=$true)][string]$Path)

    # Protect the root once. Children inherit this policy; stripping inheritance
    # recursively can leave existing files inaccessible after installation.
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
        $identity = New-Object System.Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
            $identity, 'FullControl', 'ContainerInherit, ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
    # Reset existing children too, including protected ACLs from older installers.
    & icacls.exe (Join-Path $Path '*') /reset /T /Q
    if ($LASTEXITCODE -ne 0) { throw 'Failed to secure application data files' }
}
