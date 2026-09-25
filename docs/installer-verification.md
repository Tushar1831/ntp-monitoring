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
