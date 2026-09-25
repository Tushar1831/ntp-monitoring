import socket
import struct
import unittest
from unittest.mock import Mock, patch

from ntp_client.ntp_query import NTP_DELTA, NtpQueryError, query_ntp_server


def packet(receive=1001.25, transmit=1001.5, stratum=2, leap=0):
    data = bytearray(48)
    data[0] = (leap << 6) | (3 << 3) | 4
    data[1] = stratum
    for position, timestamp in ((24, 1000.0), (32, receive), (40, transmit)):
        if timestamp is not None:
            value = timestamp + NTP_DELTA
            struct.pack_into('!II', data, position, int(value), int((value % 1) * 2**32))
    return bytes(data)


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.sock = Mock()
        self.sock.getsockname.return_value = ("192.0.2.10", 50000)
        self.sock.recv.return_value = packet()
        factory = patch('ntp_client.ntp_query.socket.socket', return_value=self.sock)
        factory.start()
        self.addCleanup(factory.stop)
        clock = patch('ntp_client.ntp_query.time.time', side_effect=[1000.0, 1000.5])
        clock.start()
        self.addCleanup(clock.stop)

    def test_positive_offset_delay_and_wire_request(self):
        result = query_ntp_server('primary.test', timeout=3)
        self.assertAlmostEqual(result['offset_seconds'], 1.125)
        self.assertAlmostEqual(result['delay_seconds'], 0.25)
        self.assertEqual(result['stratum'], 2)
        self.assertEqual(result['local_ip'], '192.0.2.10')
        self.assertFalse(result['unsynchronized'])
        sent = self.sock.send.call_args[0][0]
        self.sock.connect.assert_called_once_with(('primary.test', 123))
        self.assertEqual(len(sent), 48)
        self.assertEqual(sent[0], 27)
        self.assertEqual(struct.unpack('!II', sent[40:48]), (NTP_DELTA + 1000, 0))
        self.sock.settimeout.assert_called_once_with(3)
        self.sock.close.assert_called_once_with()

    def test_negative_offset(self):
        self.sock.recv.return_value = packet(999.25, 999.5)
        self.assertAlmostEqual(query_ntp_server('primary.test')['offset_seconds'], -0.875)

    def test_unsynchronized_response_rejected(self):
        self.sock.recv.return_value = packet(leap=3)
        self.assert_query_error('unsynchronized')

    def assert_query_error(self, message):
        with self.assertRaisesRegex(NtpQueryError, message):
            query_ntp_server('primary.test')
        self.sock.close.assert_called_once_with()

    def test_timeout(self):
        self.sock.recv.side_effect = socket.timeout()
        self.assert_query_error('Timed out')

    def test_dns_failure(self):
        self.sock.send.side_effect = socket.gaierror('unknown host')
        self.assert_query_error('DNS resolution failed')

    def test_send_failure(self):
        self.sock.send.side_effect = OSError('network unavailable')
        self.assert_query_error('Failed to send')

    def test_receive_failure(self):
        self.sock.recv.side_effect = OSError('connection refused')
        self.assert_query_error('Connection error')

    def test_short_response(self):
        self.sock.recv.return_value = b'bad'
        self.assert_query_error('Malformed response')

    def test_server_denial(self):
        data = bytearray(packet(stratum=0))
        data[12:16] = b'RATE'
        self.sock.recv.return_value = bytes(data)
        self.assert_query_error('RATE')

    def test_empty_timestamp(self):
        self.sock.recv.return_value = packet(receive=None)
        self.assert_query_error('empty/unsynchronized timestamp')

    def test_reject_non_server_mode(self):
        data = bytearray(packet())
        data[0] = (3 << 3) | 3
        self.sock.recv.return_value = bytes(data)
        with self.assertRaises(NtpQueryError):
            query_ntp_server('primary.test')

    def test_reject_mismatched_originate_timestamp(self):
        data = bytearray(packet())
        data[24:32] = bytes(8)
        self.sock.recv.return_value = bytes(data)
        with self.assertRaises(NtpQueryError):
            query_ntp_server('primary.test')

    def test_invalid_stratum(self):
        self.sock.recv.return_value = packet(stratum=16)
        self.assert_query_error('invalid stratum')

    def test_invalid_version(self):
        data = bytearray(packet())
        data[0] = (7 << 3) | 4
        self.sock.recv.return_value = bytes(data)
        self.assert_query_error('unsupported NTP version')

    def test_server_time_goes_backwards(self):
        self.sock.recv.return_value = packet(receive=1002, transmit=1001)
        self.assert_query_error('inconsistent timing')

    def test_ntp_version_four_accepted(self):
        data = bytearray(packet())
        data[0] = (4 << 3) | 4
        self.sock.recv.return_value = bytes(data)
        self.assertAlmostEqual(query_ntp_server('primary.test')['offset_seconds'], 1.125)
