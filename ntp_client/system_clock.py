"""
Cross-platform helpers for setting the local system clock.

Requires elevated privileges on both platforms:
  - Windows: process must run as Administrator (SetSystemTime).
  - Linux:   process must run as root (clock_settime on CLOCK_REALTIME).

If the caller does not have sufficient privileges, ClockSyncError is
raised and the monitor loop simply logs the failure and continues
(time-difference tracking keeps working even if disciplining the
clock is not possible).
"""

import ctypes
import platform
from datetime import datetime, timezone


class ClockSyncError(Exception):
    """Raised when the local system clock could not be adjusted."""


def set_system_time_utc(utc_datetime: datetime) -> None:
    system = platform.system()
    if system == "Windows":
        _set_windows_time(utc_datetime)
    elif system == "Linux":
        _set_linux_time(utc_datetime)
    else:
        raise ClockSyncError(f"Unsupported platform for clock sync: {system}")


def _set_windows_time(utc_datetime: datetime) -> None:
    class SYSTEMTIME(ctypes.Structure):
        _fields_ = [
            ("wYear", ctypes.c_uint16),
            ("wMonth", ctypes.c_uint16),
            ("wDayOfWeek", ctypes.c_uint16),
            ("wDay", ctypes.c_uint16),
            ("wHour", ctypes.c_uint16),
            ("wMinute", ctypes.c_uint16),
            ("wSecond", ctypes.c_uint16),
            ("wMilliseconds", ctypes.c_uint16),
        ]

    st = SYSTEMTIME()
    st.wYear = utc_datetime.year
    st.wMonth = utc_datetime.month
    st.wDayOfWeek = 0
    st.wDay = utc_datetime.day
    st.wHour = utc_datetime.hour
    st.wMinute = utc_datetime.minute
    st.wSecond = utc_datetime.second
    st.wMilliseconds = int(utc_datetime.microsecond / 1000)

    kernel32 = ctypes.windll.kernel32
    if not kernel32.SetSystemTime(ctypes.byref(st)):
        err = ctypes.GetLastError()
        raise ClockSyncError(
            f"SetSystemTime failed (WinError {err}). "
            "The process must be run elevated (Administrator)."
        )


def _set_linux_time(utc_datetime: datetime) -> None:
    timestamp = utc_datetime.timestamp()
    CLOCK_REALTIME = 0

    class timespec(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_long), ("tv_nsec", ctypes.c_long)]

    ts = timespec()
    ts.tv_sec = int(timestamp)
    ts.tv_nsec = int((timestamp - int(timestamp)) * 1e9)

    try:
        librt = ctypes.CDLL("librt.so.1", use_errno=True)
    except OSError:
        librt = ctypes.CDLL("libc.so.6", use_errno=True)

    result = librt.clock_settime(CLOCK_REALTIME, ctypes.byref(ts))
    if result != 0:
        errno = ctypes.get_errno()
        raise ClockSyncError(
            f"clock_settime failed (errno {errno}). "
            "The process must be run as root."
        )
