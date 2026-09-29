"""
Minimal SNTP client implementation (RFC 4330 / RFC 5905 subset).

Implemented from scratch against the raw UDP protocol so the whole
application has zero third-party dependencies (stdlib only: socket,
struct, time). This makes it trivial to deploy on any Windows or
Linux machine that has Python 3.7+, with nothing to `pip install`.
"""

import socket
import struct
import time

NTP_PORT = 123
NTP_DELTA = 2208988800  # seconds between 1900-01-01 (NTP epoch) and 1970-01-01 (Unix epoch)
NTP_ERA_SECONDS = 2 ** 32
CLOCK_STEP_TOLERANCE = 0.1  # Allow scheduling/timestamp noise, reject clock steps.
NEGATIVE_DELAY_TOLERANCE = 0.001
NTP_PACKET_FORMAT = "!B B B b 11I"  # 48-byte NTP packet header


class NtpQueryError(Exception):
    """Raised when an NTP server cannot be reached or returns an invalid/denied response."""


class NtpResponseError(NtpQueryError):
    """A reachable server returned a response unsafe for synchronization."""


def _to_ntp_timestamp(unix_time):
    return unix_time + NTP_DELTA


def _read_ntp_timestamp(data, offset, reference_time):
    seconds, fraction = struct.unpack("!II", data[offset:offset + 8])
    if seconds == 0 and fraction == 0:
        return 0.0
    value = seconds + fraction / 2 ** 32
    # The wire format has no era number. Select the era nearest the local
    # clock, which must be approximately correct (within 68 years).
    era = round((reference_time + NTP_DELTA - value) / NTP_ERA_SECONDS)
    return value + era * NTP_ERA_SECONDS - NTP_DELTA


def query_ntp_server(server, port=NTP_PORT, timeout=5, version=3):
    """
    Query an SNTP/NTP server once and return timing details.

    Returns a dict with:
        server, offset_seconds, delay_seconds, stratum,
        leap_indicator, t1..t4 (raw timestamps)

    Raises NtpQueryError on any failure: DNS resolution failure,
    socket timeout, connection refused/unreachable, malformed
    response, or a kiss-of-death (stratum 0) denial from the server.
    """
    if not server:
        raise NtpQueryError("No server address configured")

    packet = bytearray(48)
    # LI = 0 (no warning), VN = version, Mode = 3 (client)
    packet[0] = (0 << 6) | (version << 3) | 3

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        try:
            # Connected UDP filters replies to the selected peer address/port.
            sock.connect((server, port))
            local_ip = sock.getsockname()[0]

            t1 = time.time()  # client transmit time (T1), local system clock, UTC-based
            monotonic_t1 = time.monotonic()
            t1_ntp = _to_ntp_timestamp(t1)
            seconds = int(t1_ntp)
            fraction = int((t1_ntp - seconds) * (2 ** 32))
            struct.pack_into("!II", packet, 40, seconds % NTP_ERA_SECONDS, fraction)
            sock.send(bytes(packet))
        except socket.gaierror as e:
            raise NtpQueryError(f"DNS resolution failed for '{server}': {e}") from e
        except OSError as e:
            raise NtpQueryError(f"Failed to send request to '{server}': {e}") from e

        try:
            data = sock.recv(1024)
            t4 = time.time()  # Capture arrival before cleanup/parsing.
            monotonic_t4 = time.monotonic()
        except socket.timeout as e:
            raise NtpQueryError(f"Timed out waiting for response from '{server}' ({timeout}s)") from e
        except OSError as e:
            raise NtpQueryError(f"Connection error contacting '{server}': {e}") from e
    finally:
        sock.close()

    if len(data) < 48:
        raise NtpResponseError(f"Malformed response from '{server}' ({len(data)} bytes, expected >= 48)")

    li_vn_mode, stratum, poll, precision = struct.unpack("!B B B b", data[0:4])
    leap_indicator = (li_vn_mode >> 6) & 0x3
    response_version = (li_vn_mode >> 3) & 0x7
    if response_version not in (3, 4):
        raise NtpResponseError(f"Server '{server}' returned unsupported NTP version {response_version}")
    if li_vn_mode & 0x7 != 4:
        raise NtpResponseError(f"Server '{server}' returned non-server mode")
    if data[24:32] != packet[40:48]:
        raise NtpResponseError(f"Server '{server}' returned mismatched originate timestamp")
    ref_id_raw = data[12:16]

    if stratum == 0:
        # Kiss-of-death: server explicitly refused/denied the request
        kiss_code = ref_id_raw.decode("ascii", errors="replace").strip("\x00")
        raise NtpResponseError(f"Server '{server}' returned kiss-of-death / denied request (code: {kiss_code or 'unknown'})")

    if not 1 <= stratum <= 15:
        raise NtpResponseError(f"Server '{server}' returned invalid stratum {stratum}")
    if leap_indicator == 3:
        raise NtpResponseError(f"Server '{server}' reports unsynchronized time (leap indicator 3)")

    t2 = _read_ntp_timestamp(data, 32, t1)  # server receive time
    t3 = _read_ntp_timestamp(data, 40, t1)  # server transmit time

    if t2 == 0.0 or t3 == 0.0:
        raise NtpResponseError(f"Server '{server}' returned an empty/unsynchronized timestamp")

    if t3 < t2 or t4 < t1:
        raise NtpResponseError(f"Server '{server}' returned inconsistent timing or local clock moved backwards")
    if abs((t4 - t1) - (monotonic_t4 - monotonic_t1)) > CLOCK_STEP_TOLERANCE:
        raise NtpResponseError('Local clock changed during the query; sample discarded')

    offset_seconds = ((t2 - t1) + (t3 - t4)) / 2.0
    delay_seconds = (t4 - t1) - (t3 - t2)
    if delay_seconds < -NEGATIVE_DELAY_TOLERANCE:
        raise NtpResponseError('Server processing time exceeds the measured exchange; sample discarded')


    return {
        "server": server,
        "local_ip": local_ip,
        "offset_seconds": offset_seconds,
        "delay_seconds": max(delay_seconds, 0.0),
        "stratum": stratum,
        "leap_indicator": leap_indicator,
        "unsynchronized": leap_indicator == 3,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "t4": t4,
        "monotonic_t4": monotonic_t4,
    }
