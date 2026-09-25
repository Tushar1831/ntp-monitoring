# XML output contract

The application writes both files in the configured `log_directory` (the supplied
config uses `./logs`, relative to the config file). This resolves the draft BRD's
snapshot/history ambiguity by providing both; stakeholder sign-off is still needed.

- `<workstation>_ntpstatus.xml`: one current-cycle snapshot, replaced after every
  completed cycle, including fallback, monitoring-only operation, clock-setting
  failure, and total outage. It does not rotate or accumulate history.
- `<workstation>_ntplog.xml`: existing event history, with existing daily rotation
  and entry retention options. Existing field names and root remain unchanged.

The versioned snapshot schema is [ntp-status-v1.xsd](../schemas/ntp-status-v1.xsd).
Consumers should check `schemaVersion`, `status`, `SyncStatus`, and freshness of
`CurrentSystemTime`; the presence of a file alone does not imply synchronization.
No XML namespace is used. All snapshot elements are always present in schema order.
Unavailable values use empty elements, never a fabricated IP or zero offset.

| BRD field | Snapshot element and meaning |
|---|---|
| FR-22a host | `WorkstationName`: configured override or detected hostname |
| FR-22b endpoint IP | `IPAddress`: local IPv4 address selected for the successful NTP socket, not the server IP |
| FR-22c time source | `PrimaryNTPServer`: configured primary; `ActiveNTPServer` and `ActiveServerRole`: source used this cycle |
| FR-22d system time | `CurrentSystemTime`: UTC ISO 8601 timestamp at snapshot construction, after any attempted adjustment |
| FR-22e correction | `AppliedCorrectionMilliseconds`: signed correction accepted by the OS this cycle, zero when skipped/failed |

`MeasuredOffsetMilliseconds` is separate from correction applied. `SyncStatus`
is `applied`, `skipped`, or `failed`; `SyncReason` explains why, using the values
in the README. `Message` includes clock-setting errors. OS acceptance does not
prove independently measured accuracy or the exact step after API rounding/latency.
The correction is for this cycle, not a carried-forward value from an older sync.

`SecondaryNTPServer` is empty when unconfigured. If no usable source exists,
`ActiveNTPServer`, `ActiveServerRole`, `MeasuredOffsetMilliseconds`, and `IPAddress`
are empty; `IPAddressSource` is `unavailable`. On a successful query it is
`ntp_socket`. This explicitly reports missing information during an outage rather
than guessing among interfaces or carrying forward an old address.

`Attempts/Attempt` records each query in order, with `status`, `Server`,
`ServerRole`, `Reason` (`usable_response`, `invalid_response`, or `query_failed`),
and `Message`. A successful query can still be followed by a failed clock set.
The root `status` is `failure` if no usable time was obtained or clock setting
failed; otherwise it is `success`. Monitoring-only cycles can therefore be
successful while `SyncStatus` is `skipped`.

Each file is replaced atomically, but the pair is not a transaction. A filesystem
error or unexpected exception can prevent snapshot publication; the old snapshot
remains, so consumers must detect stale timestamps. History is written first.
Snapshots and event logs are not tamper-evident. Daily rotation applies only to
history. Neither format implements centralized collection or retention by age.
