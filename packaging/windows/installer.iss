#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
[Setup]
AppId={{5E6DAD37-A588-4DA9-B3E5-3A8520ED7C37}
AppName=NTP Client Monitor
AppVersion={#AppVersion}
DefaultDirName={autopf}\NTP Client Monitor
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\..\artifacts
OutputBaseFilename=ntp-monitor-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\cli\ntp-monitor.exe
CloseApplications=yes
CloseApplicationsFilter=ntp-monitor-gui.exe
RestartApplications=no

[Dirs]
Name: "{commonappdata}\NTPClientMonitor"
Name: "{commonappdata}\NTPClientMonitor\logs"

[Files]
Source: "..\..\dist\ntp-monitor\*"; DestDir: "{app}\cli"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\ntp-monitor-service\*"; DestDir: "{app}\service"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\ntp-monitor-gui\*"; DestDir: "{app}\gui"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\config.json"; DestDir: "{commonappdata}\NTPClientMonitor"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "service.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "service.ps1"; Flags: dontcopy
Source: "..\..\schemas\*"; DestDir: "{app}\schemas"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\NTP Client Monitor"; Filename: "{app}\gui\ntp-monitor-gui.exe"

[Code]
function ServiceCommand(Script, Action, Directory: String): Boolean;
var Code: Integer; Args: String;
begin
  Args := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + Script + '" -Action ' + Action;
  if Directory <> '' then Args := Args + ' -InstallDirectory "' + Directory + '"';
  Result := Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Args,
    '', SW_HIDE, ewWaitUntilTerminated, Code);
  if Result then Result := Code = 0;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  ExtractTemporaryFile('service.ps1');
  if not ServiceCommand(ExpandConstant('{tmp}\service.ps1'), 'Stop', '') then
    Result := 'Could not stop NTPClientMonitor. No application files have been replaced.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer;
begin
  if CurStep = ssPostInstall then begin
    if not Exec(ExpandConstant('{app}\cli\ntp-monitor.exe'), '--check-config', '',
      SW_HIDE, ewWaitUntilTerminated, Code) then
      RaiseException('Could not run configuration validation.');
    if Code <> 0 then
      RaiseException('Configuration validation failed. Correct ProgramData\NTPClientMonitor\config.json and rerun setup.');
    if not ServiceCommand(ExpandConstant('{app}\service.ps1'), 'Install', ExpandConstant('{app}')) then
      RaiseException('Service installation/start failed. Inspect the Windows Application log and rerun setup.');
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := ServiceCommand(ExpandConstant('{app}\service.ps1'), 'Remove', '');
  if not Result then MsgBox('Could not remove the service. Uninstall cancelled.', mbError, MB_OK);
end;
