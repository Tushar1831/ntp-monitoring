import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from ntp_client.xml_logger import XmlLogger


class XmlTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name) / 'logs'
        self.logger = XmlLogger(str(self.directory), 'host-test')

    def entries(self):
        return ET.parse(self.logger.current_log_path()).getroot().findall('Entry')

    def test_creates_directory_and_serializes_fields(self):
        self.logger.log_entry('TimeCheck', 'success', server='time.test',
                              server_role='primary', offset_ms=-1.25,
                              roundtrip_ms=2.5, stratum=2, clock_synced=False,
                              message='a < b & c')
        root = ET.parse(self.logger.current_log_path()).getroot()
        self.assertEqual(root.attrib['workstation'], 'host-test')
        entry = root.find('Entry')
        self.assertEqual(entry.attrib['event'], 'TimeCheck')
        self.assertIsNotNone(datetime.fromisoformat(entry.attrib['timestamp']).tzinfo)
        expected = {'Server': 'time.test', 'ServerRole': 'primary',
                    'OffsetMilliseconds': '-1.250', 'RoundtripMilliseconds': '2.500',
                    'Stratum': '2', 'ClockSynced': 'false', 'Message': 'a < b & c'}
        self.assertEqual({child.tag: child.text for child in entry}, expected)

    def test_history_survives_new_logger_instance(self):
        self.logger.log_entry('ConnectionLost', 'failure')
        XmlLogger(str(self.directory), 'host-test').log_entry('TimeCheck', 'success')
        self.assertEqual([e.attrib['event'] for e in self.entries()],
                         ['ConnectionLost', 'TimeCheck'])

    def test_corrupt_log_preserved(self):
        path = Path(self.logger.current_log_path())
        path.write_text('<broken', encoding='utf-8')
        self.logger.log_entry('TimeCheck', 'success')
        backups = list(self.directory.glob('*.corrupt.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), '<broken')
        self.assertEqual(len(self.entries()), 1)

    def test_failed_replace_preserves_previous_xml(self):
        self.logger.log_entry('TimeCheck', 'success')
        path = Path(self.logger.current_log_path())
        before = path.read_bytes()
        with patch('ntp_client.xml_logger.os.replace', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                self.logger.log_entry('ConnectionLost', 'failure')
        self.assertEqual(path.read_bytes(), before)

    def test_unwritable_output_reports_error(self):
        with patch('builtins.open', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                self.logger.log_entry('TimeCheck', 'success')

    def test_daily_rotation_changes_filename(self):
        self.logger.rotation = 'daily'
        with patch('ntp_client.xml_logger.datetime') as clock:
            clock.now.return_value = datetime(2026, 9, 25)
            first = self.logger.current_log_path()
            clock.now.return_value = datetime(2026, 9, 26)
            second = self.logger.current_log_path()
        self.assertEqual(Path(first).name, 'host-test_ntplog_20260925.xml')
        self.assertEqual(Path(second).name, 'host-test_ntplog_20260926.xml')

    def test_retention_preserves_entries_below_cap(self):
        self.logger.max_entries = 4
        for index in range(3):
            self.logger.log_entry('TimeCheck', 'success', message=str(index))
        self.assertEqual([e.findtext('Message') for e in self.entries()], ['0', '1', '2'])

    def test_retention_removes_only_oldest_above_cap(self):
        for index in range(4):
            self.logger.log_entry('TimeCheck', 'success', message=str(index))
        self.logger.max_entries = 4
        self.logger.log_entry('TimeCheck', 'success', message='4')
        self.assertEqual([e.findtext('Message') for e in self.entries()], ['1', '2', '3', '4'])
