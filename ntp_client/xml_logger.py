"""
XML log writer.

Writes one XML file per workstation (and optionally per day) named:
    <workstationname>_ntplog.xml
or, with daily rotation enabled:
    <workstationname>_ntplog_YYYYMMDD.xml

Each call to log_entry() appends a single <Entry> element to the
document and rewrites the file atomically (write to a temp file,
then os.replace) so a log viewer or another process reading the file
-- including over a network share -- never sees a half-written file.
"""

import os
import platform
import socket
import threading
from datetime import datetime, timezone
from xml.dom import minidom
from xml.etree import ElementTree as ET


class XmlLogger:
    def __init__(self, log_directory, workstation_name=None, rotation="none", max_entries=None):
        self.log_directory = log_directory
        self.workstation_name = workstation_name or socket.gethostname()
        self.rotation = rotation  # "none" | "daily"
        self.max_entries = max_entries
        self._lock = threading.Lock()
        os.makedirs(self.log_directory, exist_ok=True)

    def current_log_path(self):
        base = f"{self.workstation_name}_ntplog"
        if self.rotation == "daily":
            base += "_" + datetime.now().strftime("%Y%m%d")
        return os.path.join(self.log_directory, base + ".xml")

    def current_status_path(self):
        return os.path.join(self.log_directory, self.workstation_name + '_ntpstatus.xml')

    def write_status(self, primary_server, secondary_server, attempts, status,
                     server, server_role, local_ip, offset_ms, sync):
        """Replace the versioned current-cycle snapshot; history is separate."""
        with self._lock:
            root = ET.Element('NTPClientStatus', schemaVersion='1.0', status=status)
            fields = {
                'WorkstationName': self.workstation_name,
                'IPAddress': local_ip,
                'IPAddressSource': 'ntp_socket' if local_ip else 'unavailable',
                'PrimaryNTPServer': primary_server,
                'SecondaryNTPServer': secondary_server,
                'ActiveNTPServer': server,
                'ActiveServerRole': server_role,
                'CurrentSystemTime': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                'MeasuredOffsetMilliseconds': None if offset_ms is None else f'{offset_ms:.3f}',
                'AppliedCorrectionMilliseconds': f"{sync['applied_ms']:.3f}",
                'SyncStatus': sync['status'],
                'SyncReason': sync['reason'],
                'Message': sync.get('message'),
            }
            for name, value in fields.items():
                element = ET.SubElement(root, name)
                if value is not None:
                    element.text = str(value)
            attempt_list = ET.SubElement(root, 'Attempts')
            for attempt in attempts:
                entry = ET.SubElement(attempt_list, 'Attempt', status=attempt['status'])
                for name, key in (('Server', 'server'), ('ServerRole', 'role'),
                                  ('Reason', 'reason'), ('Message', 'message')):
                    ET.SubElement(entry, name).text = attempt[key]
            path = self.current_status_path()
            self._write_atomic(root, path)
            return path

    def _load_or_create_root(self, path):
        if os.path.exists(path):
            try:
                tree = ET.parse(path)
                return tree.getroot()
            except ET.ParseError:
                # File is corrupted (e.g. truncated by a crash/power loss) -- preserve it
                # for forensics and start a fresh log rather than losing new data.
                backup = f"{path}.corrupt.{datetime.now().strftime('%Y%m%d%H%M%S')}"
                try:
                    os.rename(path, backup)
                except OSError:
                    pass
        root = ET.Element("NTPMonitorLog")
        root.set("workstation", self.workstation_name)
        root.set("platform", f"{platform.system()} {platform.release()}")
        return root

    def log_entry(self, event_type, status, server=None, server_role=None,
                  offset_ms=None, roundtrip_ms=None, stratum=None,
                  clock_synced=None, message=None, consecutive_failures=None,
                  sync_status=None, sync_reason=None, applied_correction_ms=None):
        """
        Append one log entry. Only fields that are not None are written.

        event_type: "TimeCheck" | "ConnectionLost" | "ConnectionRestored" | "AllServersUnreachable"
        status:     "success" | "failure" | "critical"
        """
        with self._lock:
            path = self.current_log_path()
            root = self._load_or_create_root(path)

            entry = ET.SubElement(root, "Entry")
            entry.set("timestamp", datetime.now(timezone.utc).isoformat(timespec="milliseconds"))
            entry.set("event", event_type)
            entry.set("status", status)

            fields = {
                "Server": server,
                "ServerRole": server_role,
                "OffsetMilliseconds": None if offset_ms is None else f"{float(offset_ms):.3f}",
                "RoundtripMilliseconds": None if roundtrip_ms is None else f"{float(roundtrip_ms):.3f}",
                "Stratum": stratum,
                "ClockSynced": None if clock_synced is None else str(bool(clock_synced)).lower(),
                "ConsecutiveFailures": consecutive_failures,
                "Message": message,
                "SyncStatus": sync_status,
                "SyncReason": sync_reason,
                "AppliedCorrectionMilliseconds": None if applied_correction_ms is None else f"{float(applied_correction_ms):.3f}",
            }
            for tag, value in fields.items():
                if value is None:
                    continue
                sub = ET.SubElement(entry, tag)
                sub.text = str(value)

            if self.max_entries:
                entries = root.findall("Entry")
                overflow = len(entries) - self.max_entries
                for stale in entries[:max(0, overflow)]:
                    root.remove(stale)

            self._write_atomic(root, path)
            return path

    @staticmethod
    def _write_atomic(root, path):
        rough = ET.tostring(root, encoding="unicode")
        pretty = minidom.parseString(rough).toprettyxml(indent="  ")
        pretty = "\n".join(line for line in pretty.split("\n") if line.strip())
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(pretty)
        os.replace(tmp_path, path)
