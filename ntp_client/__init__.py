"""
NTP Client Monitor
-------------------
A lightweight, dependency-free (stdlib-only) NTP client/monitor for
Windows and Linux. Polls a primary and secondary NTP server on a
configurable interval, tracks the precise time offset between the
local machine and the NTP server, optionally disciplines the local
system clock, and writes structured XML logs (including connection
loss / restoration events), similar in spirit to a PRTG NTP sensor.
"""

__version__ = "1.0.0"
