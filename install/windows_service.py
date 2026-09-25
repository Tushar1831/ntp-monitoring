"""
Optional: run the NTP monitor as a native Windows service using pywin32.

This is NOT required -- NSSM (see README) is the simpler option and needs
no extra Python packages. Use this file only if you specifically want a
pywin32-based service and are comfortable installing pywin32.

Setup:
    pip install pywin32
    python windows_service.py install
    python windows_service.py start

    (run an elevated/Administrator command prompt for install/start,
     and for clock-sync to actually be permitted at runtime)

Uninstall:
    python windows_service.py stop
    python windows_service.py remove
"""

import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import servicemanager  # noqa: E402
import win32event  # noqa: E402
import win32service  # noqa: E402
import win32serviceutil  # noqa: E402

from ntp_client.config import load_config  # noqa: E402
from ntp_client.monitor import NtpMonitor  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
if getattr(sys, "frozen", False):
    CONFIG_PATH = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                               "NTPClientMonitor", "config.json")


class NtpMonitorService(win32serviceutil.ServiceFramework):
    _svc_name_ = "NTPClientMonitor"
    _svc_display_name_ = "NTP Client Monitor Service"
    _svc_description_ = (
        "Polls primary/secondary NTP servers, tracks time offset, "
        "optionally disciplines the system clock, and writes XML logs."
    )

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.stop_event)
        self.running = False

    def SvcDoRun(self):
        try:
            config = load_config(CONFIG_PATH)
            os.makedirs(config["log_directory"], exist_ok=True)
            logging.basicConfig(
                filename=os.path.join(config["log_directory"], "service_debug.log"),
                level=logging.INFO,
                format="%(asctime)s [%(levelname)s] %(message)s",
            )
            monitor = NtpMonitor(config)
        except (OSError, ValueError) as e:
            servicemanager.LogErrorMsg(f"NTP monitor startup failed: {e}")
            raise
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        interval = config.get("check_interval_seconds", 300)

        while self.running:
            start = time.monotonic()
            try:
                monitor.check_once()
            except Exception:
                logging.exception("Error during monitor cycle")
            elapsed = time.monotonic() - start
            wait_ms = max(0, int((interval - elapsed) * 1000))
            rc = win32event.WaitForSingleObject(self.stop_event, wait_ms)
            if rc == win32event.WAIT_OBJECT_0:
                break


if __name__ == "__main__":
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(NtpMonitorService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(NtpMonitorService)
