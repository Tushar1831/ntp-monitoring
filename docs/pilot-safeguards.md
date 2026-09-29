# Pilot synchronisation safeguards

Clock adjustment remains off by default. Monitoring still records large offsets
when adjustment is disabled. If enabled, the default maximum automatic correction
is five seconds in either direction. This is a conservative application default,
not a guarantee of accuracy or an NTP standard requirement.

Open Settings and change **Maximum automatic correction (seconds)** to configure
`max_clock_correction_seconds`. Existing configurations inherit the five-second
default. The value must be positive and finite; the minimum correction threshold
must not exceed it. A correction exactly at the maximum is allowed. A larger
correction is blocked: the latest status and history report `SyncStatus=failed`,
`SyncReason=correction_limit_exceeded`, and zero applied correction. The measured
offset is retained. Review the time source and local clock before changing the
limit; increasing it is not the normal response to an unexpected large offset.

Queries compare wall-clock elapsed time with monotonic elapsed time. A discrepancy
greater than 100 ms rejects the sample and allows normal fallback to the secondary
server. A clock step detected after measurement also blocks adjustment, with
`SyncReason=local_clock_changed`. These checks reduce races with other clock
adjustments but cannot eliminate a change between the final check and OS call.
The pilot deployment should have one designated clock-adjustment authority.

Responses claiming server processing time more than 1 ms longer than the entire
exchange are rejected. Smaller negative delays, possible from timestamp noise,
are reported as zero. These tolerances do not guarantee sub-millisecond accuracy.

NTP timestamps now wrap at the 2036 era boundary and are decoded relative to the
local date. The local date must be within approximately 68 years of the server.
An all-zero server timestamp remains reserved for unknown time and is rejected.

The existing version 1 XML schema is preserved. Safety blocks use the existing
`failed` outcome with specific reasons and explanatory messages.

## Pilot acceptance checks

- Verify ordinary monitoring and primary/secondary failover on the target network.
- In a disposable VM, verify offsets within the configured limit can be corrected
  in both directions, with no competing OS time service adjusting the clock.
- Verify larger offsets leave the clock untouched and show the failure reason in
  the desktop, status XML and history XML.
- Confirm reboot, upgrade and service recovery with the newly built installer.
- Measure clock accuracy independently after correction; an `applied` record means
  the OS accepted the requested time, not that accuracy was independently verified.

Automated tests simulate clock changes and never adjust the host clock. Native
Windows/Linux acceptance remains necessary. This change does not add NTS,
multi-sample filtering, agreement between servers, tamper-proof logs, or signed
releases. It does not authenticate a responding time server.

## Verification of this change

All 96 unit tests passed on the development host. The first-run desktop smoke
test passed on Ubuntu 22.04 with a virtual display, including saving a customised
maximum correction, cancelling setup, and repairing invalid configuration.
Service startup in that GUI test is mocked. Windows installer rebuilds and real
clock-adjustment acceptance tests have not been performed for this change.
