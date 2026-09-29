# NTP Client Monitor

**Installing the app?** Follow the [end-user installation guide](docs/install-app.md).
Use a built setup EXE (Windows) or DEB/RPM (Linux), not the source ZIP.
Fresh installs open first-run setup; **Save and start** configures background startup.
No terminal, Python, or build tools are needed by end users.



A lightweight, **dependency-free** (Python 3.7+ standard library only) NTP
client/monitor for **Windows and Linux**. It behaves like a PRTG NTP sensor:

- Polls a **primary** NTP server every N seconds (default 300 = 5 minutes),
  falling back to a **secondary** server if the primary doesn't answer.
- Computes the **precise time offset** and **round-trip delay** between the
  local machine and the NTP server on every cycle (standard SNTP algorithm,
  RFC 4330/5905).
- Optionally **disciplines the local system clock** (Windows: `SetSystemTime`;
  Linux: `clock_settime`) — requires Administrator/root.
- Writes an **XML log** per workstation, named `<workstationname>_ntplog.xml`,
  to a local folder or a network/UNC path.
- Logs **connection loss** (`ConnectionLost`) for each server that fails, and
  a `ConnectionRestored` entry when connectivity returns. If both servers
  fail in the same cycle, an `AllServersUnreachable` (critical) entry is
  written.

No third-party packages are required for the core monitor (it implements
the NTP wire protocol itself with `socket`/`struct`), so it runs on a bare
Python install with nothing to `pip install`.

## Standalone installers and platform targets

Installer build scripts bundle Python and dependencies and register background
services. Target platforms are **x64 Windows 10/11, Windows Server 2019+,
Ubuntu 22.04+, and RHEL-compatible 9 systems** (Linux x86-64 with systemd).
ARM and Alpine Linux are not currently package targets. Targeted does not mean
verified on every listed OS; see [installer build and verification instructions](docs/installers.md).

Current evidence: version 1.1.0 Linux package checks passed without system Python;
first-run GUI tests and the DEB pending-setup/service lifecycle passed in containers.
Windows build/testing and real VM reboot checks remain outstanding. See the
[verification record](docs/installer-verification.md) for exact scope.

Windows uses a setup EXE; Linux uses DEB/RPM. Endpoints do not need a separately
installed Python, pywin32, pip, or NSSM. Linux still needs its OS libraries and
systemd. Configuration and logs are kept outside the binaries and preserved on
upgrade. New installs start in monitoring-only mode.

The older instructions below describe running **from Python source**. For a
standalone installation, use the installer guide linked above.

## Desktop window

A simple **Network Time** window shows endpoint/service status, server results,
last correction, recent events, and XML diagnostics. Settings cover all existing
configuration options, with Start/Stop and Check now controls for the installed
service. Closing the window leaves monitoring running.

Run `python3 gui.py --config /path/to/config.json` from source, or use the desktop
shortcut in new installer builds. See [desktop usage and verification](docs/desktop.md).
The GUI uses Tk; installers bundle its Python/Tk runtime.

## Files

```
ntp_monitor/
  main.py                        Entry point / CLI
  config.json                    Configuration (edit this)
  ntp_client/
    ntp_query.py                 Raw SNTP protocol implementation
    system_clock.py              Cross-platform clock-set (Win/Linux)
    xml_logger.py                XML log writer (atomic writes)
    monitor.py                   Poll loop, failover, offset tracking
  install/
    windows_service.py           Optional pywin32-based Windows service
    linux/ntp-monitor.service    systemd unit file
```

## Configuration (`config.json`)

| Key | Meaning |
|---|---|
| `primary_server` | Hostname/IP of the primary NTP server (required) |
| `secondary_server` | Hostname/IP of the secondary/fallback server (optional) |
| `check_interval_minutes` | Whole minutes between polls, 1–15 (default `5`) |
| `check_interval_seconds` | Legacy alternative: whole seconds, 60–900; do not specify both interval keys |
| `timeout_seconds` | Positive finite timeout per server, no greater than the interval (default `5`) |
| `log_directory` | Local path or network/UNC path (e.g. `\\\\fileserver\\logs`) for XML logs |
| `log_rotation` | `"none"` (one growing file) or `"daily"` (`_YYYYMMDD` suffix) |
| `max_log_entries_per_file` | Positive integer cap (default `20000`); `null` disables trimming |
| `sync_system_clock` | `true` to actually set the local clock; `false` to just monitor/log |
| `resync_threshold_seconds` | Nonnegative finite threshold (default `0.5`); `null` disables the threshold |
| `max_clock_correction_seconds` | Positive finite maximum automatic correction in either direction (default `5`); larger offsets are logged as failures without changing the clock |
| `workstation_name` | Override for the hostname used in the log filename; `null` = auto-detect |

See [pilot synchronisation safeguards](docs/pilot-safeguards.md) for correction
limits, clock-change detection, timestamp rollover handling and pilot checks.

Both the CLI and Windows service validate configuration before startup. Invalid
values fail startup with the field name in the diagnostic; Windows also reports
startup errors to the Application event log. Unknown or duplicate keys are rejected
to catch typos. Use JSON booleans (`true`/`false`), not quoted strings.

Server values must be hostnames or IPv4 addresses; IPv6 is not currently supported.
An omitted or `null` secondary disables fallback. `primary_server` and
`log_directory` are required. Relative log paths resolve from the configuration
file's directory. Workstation overrides must start with a letter/digit and contain
only letters, digits, dots, underscores, or hyphens (maximum 200 characters).
Restart the service after editing configuration; reinstalling is unnecessary.
Existing configs using `check_interval_seconds` remain supported within 60–900.

The XML file is always named `<workstation_name>_ntplog.xml` (or
`<workstation_name>_ntplog_YYYYMMDD.xml` with daily rotation), matching the
requested `workstationname_ntplog` naming convention.

## Running

```bash
# One-off check (good for testing, or for scheduling via cron/Task Scheduler
# instead of running continuously):
python3 main.py --once --verbose

# Continuous monitoring loop (polls every check_interval_seconds):
python3 main.py --verbose

# Custom config file location:
python3 main.py --config /path/to/config.json
```

Clock disciplining (`sync_system_clock: true`) requires elevated
privileges: run as **Administrator** on Windows, or as **root** on Linux.
If the process isn't elevated, the offset is still measured and logged —
only the actual clock adjustment is skipped (with a warning).

## Current-status XML

Each completed cycle also replaces `<workstation_name>_ntpstatus.xml` in the
configured log directory. It contains the host, endpoint IP, configured and active
NTP servers, report time, correction outcome, and ordered query attempts.
See the [XML output contract](docs/xml-output.md) and
[version 1 schema](schemas/ntp-status-v1.xsd) for field meanings and outage behavior.
The existing event history remains available separately.

## Sample XML log output

```xml
<?xml version="1.0" ?>
<NTPMonitorLog workstation="WKS-042" platform="Windows 10">
  <Entry timestamp="2026-09-21T05:00:00.123+00:00" event="TimeCheck" status="success">
    <Server>ntp.internal.corp</Server>
    <ServerRole>primary</ServerRole>
    <OffsetMilliseconds>12.485</OffsetMilliseconds>
    <RoundtripMilliseconds>4.201</RoundtripMilliseconds>
    <Stratum>2</Stratum>
    <ClockSynced>false</ClockSynced>
  </Entry>
  <Entry timestamp="2026-09-21T05:05:00.981+00:00" event="ConnectionLost" status="failure">
    <Server>ntp.internal.corp</Server>
    <ServerRole>primary</ServerRole>
    <ConsecutiveFailures>1</ConsecutiveFailures>
    <Message>Timed out waiting for response from 'ntp.internal.corp' (5s)</Message>
  </Entry>
  <Entry timestamp="2026-09-21T05:05:01.203+00:00" event="TimeCheck" status="success">
    <Server>time.google.com</Server>
    <ServerRole>secondary</ServerRole>
    <OffsetMilliseconds>9.112</OffsetMilliseconds>
    <RoundtripMilliseconds>21.887</RoundtripMilliseconds>
    <Stratum>1</Stratum>
    <ClockSynced>false</ClockSynced>
  </Entry>
  <Entry timestamp="2026-09-21T05:10:00.055+00:00" event="ConnectionRestored" status="success">
    <Server>ntp.internal.corp</Server>
    <ServerRole>primary</ServerRole>
    <Message>NTP connectivity restored</Message>
  </Entry>
</NTPMonitorLog>
```

## Running continuously as a service

### Windows — Option A: NSSM (simplest, no extra Python packages)

1. Download [NSSM](https://nssm.cc/download) and extract `nssm.exe`.
2. Open an elevated Command Prompt:
   ```
   nssm install NTPClientMonitor "C:\Python3\python.exe" "C:\ntp_monitor\main.py" --config "C:\ntp_monitor\config.json"
   nssm set NTPClientMonitor AppDirectory "C:\ntp_monitor"
   nssm start NTPClientMonitor
   ```
3. Run the service under an account with Administrator rights if
   `sync_system_clock` is `true` (needed for `SetSystemTime`).

### Windows — Option B: pywin32 native service

```
pip install pywin32
python install\windows_service.py install
python install\windows_service.py start
```
(from an elevated prompt). Use `stop` / `remove` to uninstall.

### Linux — systemd

```bash
sudo mkdir -p /opt/ntp-monitor
sudo cp -r ntp_client main.py config.json /opt/ntp-monitor/
sudo cp install/linux/ntp-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ntp-monitor.service
sudo systemctl status ntp-monitor.service
journalctl -u ntp-monitor.service -f
```

If you only want offset **monitoring** (not clock disciplining), edit the
`User=` line in the unit file to an unprivileged user — root is only needed
for `clock_settime`.

## Tests

Run `python3 -B -m unittest discover -s tests -v` from the project root
(use `python` on Windows). Tests require only the standard library and do not
change the system clock or contact external servers. All 96 tests pass. See
[testing documentation](docs/testing.md) for coverage, a strict
failure-reporting command, and remaining platform acceptance tests.

## Implementation notes

### Synchronization validation and audit fields

Replies must use NTP version 3 or 4, server mode, stratum 1–15, and an
originate timestamp matching the request. Empty/inconsistent timestamps and
unsynchronized servers (leap indicator 3) are rejected. Connected UDP restricts
replies to the selected peer. These checks follow the packet concepts in
[RFC 5905](https://www.rfc-editor.org/rfc/rfc5905.html); they do not authenticate
the server and do not implement NTS.

Rejected replies produce `ResponseRejected` entries and trigger secondary-server
fallback. Transport failures remain `ConnectionLost`. The existing terminal
`AllServersUnreachable` event now means no configured server supplied usable time,
including cases where servers replied but their responses were rejected.

XML time checks and failed attempts include these additional fields:

| Field | Meaning |
|---|---|
| `OffsetMilliseconds` | Measured offset, when usable time was obtained |
| `SyncStatus` | `applied`, `skipped`, or `failed` |
| `SyncReason` | `clock_set`, `disabled`, `below_threshold`, `invalid_response`, `query_failed`, `no_usable_server`, or `clock_set_failed` |
| `AppliedCorrectionMilliseconds` | Signed requested correction when the OS setter succeeded; zero when skipped or failed |
| `ClockSynced` | True only when the OS clock-setting call succeeded |
| `Message` | Response rejection or clock-setting error details, when applicable |

A clock-setting failure marks the `TimeCheck` as `status="failure"` while retaining
the measured offset. `applied` means the OS accepted the correction; it is not an
independent measurement of final clock accuracy or exact step size. OS rounding
and call latency can affect that step. A failed clock-setting call does not query
the secondary: switching servers cannot resolve a local clock-setting failure.

Polling intervals use monotonic time so a clock step does not change the wait.
XML retention now preserves all entries below the configured cap. XML remains
an ordinary local/share file, not a transactional or tamper-evident audit store:
an output failure or crash after a clock change can prevent its final record.
Actual clock-setting and service behavior still require Windows/Linux VM testing.

- The tool queries the standard NTP UDP port 123 by default (`query_ntp_server`
  accepts a `port` argument if you need a non-standard port).
- A server responding with a "kiss-of-death" / stratum-0 denial (e.g. rate
  limiting) is treated as a failure for that cycle and triggers failover to
  the secondary, exactly like a timeout.
- XML writes are atomic (written to a `.tmp` file, then renamed into place),
  so partially-written files aren't produced even when writing to a network
  share.
- If a previous log file is found corrupted (e.g. from an abrupt power
  loss), it's renamed to `*.corrupt.<timestamp>` and a fresh log is started
  rather than losing new monitoring data.
