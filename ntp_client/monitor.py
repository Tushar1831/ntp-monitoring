"""
NtpMonitor: the PRTG-style sensor loop.

Each cycle:
  1. Try the primary NTP server.
  2. On failure, fall back to the secondary NTP server.
  3. On success: log a TimeCheck entry with the precise offset/roundtrip,
     and optionally discipline the local clock.
  4. On failure of a server: log a ConnectionLost entry for that server.
  5. If BOTH servers fail in the same cycle: log an AllServersUnreachable
     (critical) entry -- this is the "server connection loss" reporting
     requirement.
  6. The next time a server responds after an outage, a ConnectionRestored
     entry is logged so the XML history shows outage start/end clearly.
"""

import logging
import math
import socket
import time
from datetime import datetime, timezone

from . import system_clock
from .ntp_query import NtpQueryError, NtpResponseError, query_ntp_server
from .xml_logger import XmlLogger

logger = logging.getLogger("ntp_monitor")


class NtpMonitor:
    def __init__(self, config):
        if not config.get("setup_complete", True):
            raise ValueError("Complete setup in NTP Client Monitor before starting monitoring")
        self.config = config
        self.workstation_name = config.get("workstation_name") or socket.gethostname()
        self.xml_logger = XmlLogger(
            log_directory=config["log_directory"],
            workstation_name=self.workstation_name,
            rotation=config.get("log_rotation", "none"),
            max_entries=config.get("max_log_entries_per_file"),
        )
        self._consecutive_failures = {"primary": 0, "secondary": 0}

    def check_once(self):
        """Publish a fresh snapshot after each completed cycle, including outages."""
        attempts = []
        report = self._check_once(attempts)
        self.xml_logger.write_status(
            primary_server=self.config['primary_server'],
            secondary_server=self.config.get('secondary_server'),
            attempts=attempts, **report,
        )

    def _check_once(self, attempts):
        """Run a single poll cycle against primary, then secondary if needed."""
        servers = [
            ("primary", self.config.get("primary_server")),
            ("secondary", self.config.get("secondary_server")),
        ]

        for role, server in servers:
            if not server:
                continue
            try:
                result = query_ntp_server(
                    server,
                    timeout=self.config.get("timeout_seconds", 5),
                )
                if result.get("unsynchronized") or not math.isfinite(result["offset_seconds"]):
                    raise NtpResponseError("Server returned unsynchronized or non-finite time")
            except NtpQueryError as e:
                attempts.append({'server': server, 'role': role, 'status': 'failure',
                                 'reason': 'invalid_response' if isinstance(e, NtpResponseError) else 'query_failed',
                                 'message': str(e)})
                self._consecutive_failures[role] += 1
                logger.warning("[%s] %s unreachable: %s", role, server, e)
                self.xml_logger.log_entry(
                    event_type="ResponseRejected" if isinstance(e, NtpResponseError) else "ConnectionLost",
                    status="failure",
                    server=server,
                    server_role=role,
                    message=str(e),
                    consecutive_failures=self._consecutive_failures[role],
                    sync_status="skipped", sync_reason="invalid_response" if isinstance(e, NtpResponseError) else "query_failed",
                    applied_correction_ms=0, clock_synced=False,
                )
                continue  # try next server in the list

            attempts.append({'server': server, 'role': role, 'status': 'success',
                             'reason': 'usable_response', 'message': ''})
            # success
            offset_ms = result["offset_seconds"] * 1000.0
            delay_ms = result["delay_seconds"] * 1000.0

            if self._consecutive_failures[role]:
                self.xml_logger.log_entry(
                    event_type="ConnectionRestored",
                    status="success",
                    server=server,
                    server_role=role,
                    message="NTP connectivity restored",
                )

            self._consecutive_failures[role] = 0
            sync = self._maybe_sync_clock(result["offset_seconds"])
            synced = sync["status"] == "applied"

            self.xml_logger.log_entry(
                event_type="TimeCheck",
                status="failure" if sync["status"] == "failed" else "success",
                server=server,
                server_role=role,
                offset_ms=offset_ms,
                roundtrip_ms=delay_ms,
                stratum=result.get("stratum"),
                clock_synced=synced,
                message=sync.get("message"),
                sync_status=sync["status"], sync_reason=sync["reason"],
                applied_correction_ms=sync["applied_ms"],
            )
            logger.info(
                "[%s] %s offset=%.3fms roundtrip=%.3fms stratum=%s sync=%s reason=%s applied=%.3fms",
                role, server, offset_ms, delay_ms, result.get("stratum"),
                sync["status"], sync["reason"], sync["applied_ms"],
            )
            return dict(status="failure" if sync['status'] == 'failed' else "success",
                        server=server, server_role=role, local_ip=result.get('local_ip'),
                        offset_ms=offset_ms, sync=sync)

        # Every configured server failed this cycle
        self.xml_logger.log_entry(
            event_type="AllServersUnreachable",
            status="critical",
            message="No configured NTP server supplied usable time this cycle",
            sync_status="skipped", sync_reason="no_usable_server",
            applied_correction_ms=0, clock_synced=False,
            consecutive_failures=max(self._consecutive_failures.values()),
        )
        logger.error("All configured NTP servers unreachable this cycle")
        return dict(status='failure', server=None, server_role=None, local_ip=None,
                    offset_ms=None, sync={'status': 'skipped', 'reason': 'no_usable_server',
                                          'applied_ms': 0.0, 'message': None})

    def _maybe_sync_clock(self, offset_seconds):
        """Report OS acceptance of a requested step, not independently measured accuracy."""
        def outcome(status, reason, applied_ms=0.0, message=None):
            return {"status": status, "reason": reason, "applied_ms": applied_ms, "message": message}

        if not math.isfinite(offset_seconds):
            return outcome("skipped", "invalid_offset")
        if not self.config.get("sync_system_clock"):
            return outcome("skipped", "disabled")
        threshold = self.config.get("resync_threshold_seconds")
        if threshold is not None and abs(offset_seconds) < threshold:
            return outcome("skipped", "below_threshold")
        try:
            corrected_ts = datetime.now(timezone.utc).timestamp() + offset_seconds
            system_clock.set_system_time_utc(datetime.fromtimestamp(corrected_ts, tz=timezone.utc))
            return outcome("applied", "clock_set", offset_seconds * 1000.0)
        except (system_clock.ClockSyncError, OSError, OverflowError, ValueError) as e:
            logger.warning("Clock sync failed: %s", e)
            return outcome("failed", "clock_set_failed", message=str(e))

    def run_forever(self):
        interval = self.config.get("check_interval_seconds", 300)
        logger.info(
            "NTP monitor started for '%s'. Interval=%ss, primary=%s, secondary=%s, log_dir=%s",
            self.workstation_name, interval,
            self.config.get("primary_server"), self.config.get("secondary_server"),
            self.config.get("log_directory"),
        )
        while True:
            cycle_start = time.monotonic()
            try:
                self.check_once()
            except Exception:
                logger.exception("Unexpected error during monitor cycle")
            elapsed = time.monotonic() - cycle_start
            time.sleep(max(0.0, interval - elapsed))
