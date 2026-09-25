# Testing

Run from the project root using Python's built-in unittest runner. No pip
packages, administrator rights, NTP connectivity, or pywin32 are needed:

```sh
python3 -B -m unittest discover -s tests -v
```

On Windows, use `python` instead of `python3`.

The suite uses temporary directories, simulated sockets, and mocked clock-setting
calls. It never sets the host clock, contacts an NTP server, or installs a service.
Monitor tests exercise real XML output together with fallback and sync decisions.

## Current baseline

All 78 tests pass with no expected failures. Previously recorded configuration,
response validation, synchronization, retention, recovery, and Windows startup
regressions are now ordinary passing tests. This is a unit-test baseline, not
Windows/Linux deployment acceptance.

The strict runner remains available and currently runs the same passing suite:

```sh
python3 -B -m tests.run_strict
```

## Coverage and remaining acceptance work

| Requirement area | Automated coverage | Still required |
| --- | --- | --- |
| FR-09–15 configuration | JSON errors, required keys, path resolution, minutes/legacy seconds, defaults, duplicate/unknown keys, type/range validation, file reload | Real service restart/reload |
| FR-16–18 query/fallback | Packet calculations, failures, primary/secondary sequence and recovery | Real UDP integration and supported network environments |
| FR-19–21 correction | Disabled mode, signed correction, thresholds, permission errors, unsynchronized-source rejection and explicit correction outcomes | Actual OS API behavior and measured accuracy in disposable VMs |
| FR-22–25 XML | Versioned snapshot fields, endpoint IP, timestamps, correction outcomes, history, outage replacement, atomic replacement failures | Stakeholder sign-off on documented snapshot/history and unavailable-IP policy |
| NFR-05–06 logging | Monitor error logging, retention regression, corruption backup, failed replace | Operational-log retention, long-running resource use, network-share outages |
| FR-01–08 services/platforms | Simulated Windows wrapper startup and invalid-config diagnostics; loop exception recovery | Windows SCM/systemd, reboot, crash restart, clean install and uninstall |
| NFR-03/04/07/08 | Not established by this suite | Permissions, authenticated NTP decision, installers, supported OS/architecture matrix |

The Windows wrapper test substitutes pywin32 modules and exercises startup file
handling only. It does not establish Windows service compatibility. Permission
failures are injected to remain deterministic even when tests run as root.
No claim of uptime, secure NTP, full BRD compliance, or Windows/Linux release
validation follows from a successful unit-test run.

Before release, test packaged artifacts on clean supported Windows/Linux VMs
without Python installed, including offline installation, boot startup, forced
termination recovery, upgrades preserving configuration, and uninstall retention.
Clock-setting integration tests must run only in disposable VMs.

Installer build/acceptance scripts are described in [installers.md](installers.md).
Their availability does not imply that a target VM test has been executed.

Desktop rendering can be checked on a display with `python3 scripts/smoke_desktop.py`
(or `xvfb-run -a python3 scripts/smoke_desktop.py` on a Linux build host).
