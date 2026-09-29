# Installer verification evidence

Recorded 26 September 2026 (Australia/Sydney). Development build 1.0.0.

| Check | Result |
|---|---|
| Local Python unit suite | 78 passed, no expected failures |
| Linux x64 frozen bundle | Built in Rocky Linux 9 with Python 3.11 / PyInstaller 6.16.0 |
| DEB and RPM packaging | Built with dpkg-deb and rpmbuild in Ubuntu 22.04 |
| Ubuntu 22.04 clean container, no Python | DEB install, offline config check, polling/XML and uninstall passed |
| Rocky Linux 9 minimal clean container, no Python | RPM install, offline config check, polling/XML and uninstall passed |
| Ubuntu 22.04 systemd container, no Python | DEB service registration, enabled/active status, forced-kill recovery, config-preserving reinstall, uninstall/log retention passed |
| Shell script syntax and workflow YAML | Passed local parser checks |
| Windows setup EXE | Build definition and acceptance script added; not compiled or executed here |
| GitHub Actions workflow | Added; not run on GitHub |
| Real Windows/Linux VM reboot and pre-login startup | Not verified |
| RPM service lifecycle on systemd | Not verified; only runtime/package installation tested |
| Actual clock correction in packaged app | Not exercised; all acceptance tests disabled clock changes |

Linux checks ran as x86-64 containers under Docker Desktop emulation on an ARM
Mac. This establishes bundled-runtime and specified container lifecycle behavior,
not full hardware/VM acceptance or validation of every targeted OS release.
The transient test containers were removed after testing.

Artifacts in the workspace:

- `artifacts/ntp-monitor_1.0.0_amd64.deb`
- `artifacts/ntp-monitor-1.0.0-1.x86_64.rpm`
- `artifacts/SHA256SUMS`

Artifacts are unsigned development builds and are ignored by source control.
The Windows artifact must be generated on Windows with the documented build
commands or workflow. No Windows executable is present in this build output.

The first Linux build image lacked a shared Python library, so the build recipe
was corrected to use Rocky Linux 9. The first Ubuntu clean-runtime check detected
Python installed through optional systemd recommendations; rerunning with
`--no-install-recommends` passed without Python. The current workflow and install
instructions use the corrected recipes.

See [installers.md](installers.md) for reproduction commands and remaining
disposable-VM acceptance steps. The service test uses the same package version
for reinstallation; cross-version migration and machine reboot remain separate
release checks.

## Desktop frontend update

The development DEB/RPM artifacts were rebuilt to include the desktop window.
The current SHA256SUMS identifies these updated files. Additional checks passed:

- Native Tk window rendering and Settings dialog in an isolated Linux display;
  closing the window made no service-control call.
- Bundled GUI launch on a fresh Ubuntu 22.04 display without system Python.
- Rebuilt DEB and RPM configuration/polling/XML checks without system Python.
- Desktop configuration-save, stale-status, history and command tests.

The earlier service lifecycle test predates the frontend addition; it was not
repeated for the GUI-enabled artifacts. Windows frontend/UAC, Linux desktop-menu
polkit authentication, and Wayland integration are not validated here.
The preview in desktop.md contains deterministic example data.

## Version 1.1.0 — first-run workflow (29 September 2026)

Built fresh DEB/RPM artifacts with `setup_complete: false`. The new acceptance
checks verified that monitoring does not begin until configuration is completed.

- 86 unit tests passed, with no expected failures.
- GUI tests passed: automatic welcome screen, cancel without starting, Save and
  start, malformed-settings repair with backup, Settings and window close.
- Ubuntu 22.04 systemd container without Python: fresh disabled/stopped state,
  completed-configuration startup, crash recovery, config-preserving reinstall,
  uninstall and retained logs passed.
- Rocky Linux 9 minimal container without Python: pending-setup exit code and
  bundled-runtime/XML tests passed.
- Linux bundle and package creation succeeded. `artifacts/SHA256SUMS` covers both
  the older 1.0.0 packages and new 1.1.0 packages; use 1.1.0 for this workflow.

The service lifecycle check supplies configuration programmatically, while the
GUI interaction test substitutes service commands. A complete desktop UAT run
with real authentication and reboot remains required. Windows build/installer
scripts and acceptance tests were updated, but no Windows executable was built
or installed in this environment.

The originally reported Windows configuration-check failure has not been
reproduced (its underlying CLI error was not supplied). The installer no longer
fails generically on editable configuration: it leaves the service stopped,
records diagnostics and opens the application for repair. Windows UTF-8 BOM
configuration files are now accepted as well.
# Windows configuration permissions regression

The Windows Actions acceptance run reported `Access is denied` when reading
`C:\ProgramData\NTPClientMonitor\config.json` after installation. The installer
now protects the data-directory root with SYSTEM/Administrators full control
and resets child ACLs to inherit that policy, replacing recursive inheritance
removal. The acceptance script also checks for an elevated administrator token
before installation so a privilege mismatch is reported directly.

`scripts/test_windows_permissions.ps1` runs in the Windows workflow and checks
existing configuration read/write access, nested files, repair of protected child
ACLs on reinstall, and inheritance for newly created files. It also rejects
unexpected permission entries. Run it only in an elevated Windows session.

The 86 Python unit tests passed locally after this change. The native Windows
permission test and rebuilt installer still require a successful Windows Actions
run; they cannot be verified on the macOS development host.
