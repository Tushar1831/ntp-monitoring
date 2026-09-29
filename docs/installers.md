# Standalone installers

Target platforms: **x64 Windows 10/11 and Windows Server 2019 or newer;
x86-64 Ubuntu 22.04 or newer and RHEL-compatible 9 distributions**. These are
the agreed targets, not a claim that every release has been tested. ARM and
Alpine/musl Linux are not supported by these packages. Linux requires systemd.

See [verification evidence](installer-verification.md) for checks actually run
and the Windows/VM verification still outstanding.

PyInstaller bundles Python and application dependencies in a directory installed
by the native installer. No separate Python, pip, pywin32, or NSSM installation
is needed on the endpoint. Linux still uses OS libraries (glibc >= 2.34 and
zlib) and systemd. Build each platform natively; a Mac cannot generate the
Windows binaries with PyInstaller.

## Maintainer build (not an end-user step)

On a Windows build machine with Python 3.11 x64 and Inno Setup 6 installed,
double-click `scripts/build_windows.cmd`. It finds per-user or machine-wide Inno
Setup, runs tests, builds the application, compiles the setup EXE, and opens the
artifacts folder. Build details are retained in `artifacts/windows-build.log`.
Send only the resulting setup EXE and end-user guide to UAT testers.

## Build

Build dependencies require internet access initially. Endpoint installers need
no Python downloads and can run offline when OS package prerequisites exist.
The version defaults to 1.1.0; change the package version for each release.

Build background: [PyInstaller platform-specific output](https://pyinstaller.org/en/stable/operating-mode.html)
and [Linux system-library limitations](https://pyinstaller.org/en/stable/usage.html).

Windows x64 build machine: install Python 3.11 x64 and Inno Setup 6, then:

```powershell
python -m pip install -r packaging/requirements-build.txt
python -B -m unittest discover -s tests -v
python scripts/build_bundle.py
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" /DAppVersion=1.1.0 packaging\windows\installer.iss
```

Linux: build the bundle on the Rocky Linux 9 / glibc 2.34 baseline container, then package it on
a Linux host with Python 3, `dpkg-deb`, `rpmbuild`, `file`, and `binutils`:

```sh
docker run --rm --platform linux/amd64 -v "$PWD:/src" -w /src \
  rockylinux:9 /bin/bash -ec '
    dnf install -y python3.11 python3.11-pip python3.11-tkinter binutils
    python3.11 -m pip install -r packaging/requirements-build.txt
    python3.11 scripts/build_bundle.py
  '
python3 scripts/build_linux_packages.py --version 1.1.0
```

Outputs are in `artifacts/`. The GitHub Actions workflow builds both platforms,
runs unit tests, and runs package/service checks. Upload this repository to GitHub
and run **Build and test installers** to execute it. Windows hosted runners
already contain Python, so that job is not clean-machine proof.

## Desktop frontend

New builds include the [Network Time desktop window](desktop.md), a Windows
Start-menu shortcut, and a Linux application-menu entry. The service continues
without the window. The GUI bundles Python and Tcl/Tk; Linux desktop OS libraries
and polkit are declared package dependencies. A graphical desktop is needed only
to open the window, not to run the service.

## Install and configure

Windows: run the setup EXE as administrator (or use `/VERYSILENT /NORESTART`).
Fresh installation registers the service as manual/stopped until GUI setup is complete. It installs binaries under `Program Files\NTP Client Monitor`, registers
`NTPClientMonitor` as a LocalSystem service, and configures crash
restarts after 10/30/60 seconds. Configuration and logs live under
`%ProgramData%\NTPClientMonitor`; local data access is limited to administrators
and SYSTEM. Edit `config.json` and restart the service to apply changes.

Ubuntu: `sudo apt install --no-install-recommends ./ntp-monitor_1.0.0_amd64.deb`.
RHEL-compatible 9: `sudo dnf install ./ntp-monitor-1.0.0-1.x86_64.rpm`.
The Linux packages install `/opt/ntp-monitor`, preserve editable configuration at
`/etc/ntp-monitor/config.json`, and write logs under `/var/log/ntp-monitor`.
They enable/start `ntp-monitor.service` only for completed, valid configuration; a container
without systemd can exercise the executable but not service lifecycle.
Use `journalctl -u ntp-monitor` for operational diagnostics.

Default configuration is monitoring-only: **clock changes are disabled**. Change
NTP sources for your network and explicitly enable `sync_system_clock` if needed.
Linux runs as root with a restricted capability set including `CAP_SYS_TIME`.
The service can write only `/var/log/ntp-monitor` by default. If selecting another
log path or a mounted share, add that path using a systemd `ReadWritePaths=`
override and grant filesystem access. Windows shares likewise need service-account
permissions. Existing native OS time synchronization must be considered before
enabling this application's clock setting.

Both bundles have an offline configuration check:

```sh
/opt/ntp-monitor/ntp-monitor --check-config
```

On Windows, use `"C:\Program Files\NTP Client Monitor\cli\ntp-monitor.exe" --check-config`.

## Upgrade and remove

Reinstalling/upgrading preserves the config and historical logs. Debian uses
conffiles, RPM uses `%config(noreplace)`, and Windows copies defaults only when
missing. Windows setup stops the existing service before replacing its files.
Invalid preserved configuration fails startup and must be corrected.

Remove via Windows Apps/Programs, `apt remove ntp-monitor`, or `dnf remove ntp-monitor`.
Services and binaries are removed; logs remain. Windows preserves the data
directory and config. Debian retains config on remove but deletes it on purge.
RPM can retain an edited config as `.rpmsave`; an unmodified default may be removed.
Uninstall does not recursively delete user log directories.

## Acceptance evidence

Run only on disposable test machines. Scripts intentionally install, terminate,
reinstall and uninstall the service, using loopback and monitoring-only mode:

```powershell
scripts\verify_windows.ps1 -Installer C:\downloads\ntp-monitor-1.0.0-windows-x64-setup.exe
```

```sh
sudo bash scripts/verify_linux_service.sh ./ntp-monitor_1.0.0_amd64.deb
# or the RPM path on a RHEL-compatible VM
```

The Windows script checks for Python on PATH; a clean VM inventory must also
confirm no Python installation outside PATH (and disable Store execution aliases).
The Linux runtime script requires no `python`/`python3` command and tests an
offline cycle and XML output in a fresh container. Service scripts check
registration, automatic-start configuration, crash recovery, config preservation
on reinstall, and uninstall/log retention. A reinstall of the same version does
not prove every future cross-version migration.

Still run a real reboot test on each target OS: install, reboot, verify service
startup before interactive login, then confirm fresh status XML. Also verify
actual clock correction in an isolated VM and your organization's network-share
permissions. Containers do not establish boot behavior or clock privilege behavior.

Packages are unsigned development artifacts. Release signing and license review
(including bundled Python/pywin32 components) remain release tasks. The RPM's
`LicenseRef-Proprietary` is placeholder metadata, not a license grant. No release
has been published by these build scripts.

For users, distribute installers with [install-app.md](install-app.md), not these developer build instructions.
