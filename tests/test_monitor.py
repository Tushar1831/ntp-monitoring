import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import call, patch
from xml.etree import ElementTree as ET

from ntp_client.monitor import NtpMonitor
from ntp_client.ntp_query import NtpQueryError, query_ntp_server
from tests.test_ntp_query import packet
from ntp_client.system_clock import ClockSyncError


class MonitorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.monitor = NtpMonitor({
            'primary_server': 'primary.test', 'secondary_server': 'secondary.test',
            'log_directory': directory.name, 'workstation_name': 'test-host',
            'sync_system_clock': False, 'resync_threshold_seconds': 0.5,
            'check_interval_seconds': 300,
        })
        query = patch('ntp_client.monitor.query_ntp_server')
        self.query = query.start()
        self.addCleanup(query.stop)
        self.result = {'offset_seconds': 1.25, 'delay_seconds': 0.025,
                       'stratum': 2, 'unsynchronized': False, 'local_ip': '192.0.2.10'}
        self.query.return_value = self.result
        clock = patch('ntp_client.monitor.system_clock.set_system_time_utc')
        self.set_clock = clock.start()
        self.addCleanup(clock.stop)
        logs = patch('ntp_client.monitor.logger')
        self.logs = logs.start()
        self.addCleanup(logs.stop)

    def entries(self):
        return ET.parse(self.monitor.xml_logger.current_log_path()).getroot().findall('Entry')

    def events(self):
        return [entry.attrib['event'] for entry in self.entries()]

    def snapshot(self):
        return ET.parse(self.monitor.xml_logger.current_status_path()).getroot()

    def test_snapshot_has_required_fields_and_utc_time(self):
        self.monitor.check_once()
        root = self.snapshot()
        self.assertEqual(root.tag, 'NTPClientStatus')
        self.assertEqual(root.attrib, {'schemaVersion': '1.0', 'status': 'success'})
        self.assertEqual(root.findtext('WorkstationName'), 'test-host')
        self.assertEqual(root.findtext('IPAddress'), '192.0.2.10')
        self.assertEqual(root.findtext('IPAddressSource'), 'ntp_socket')
        self.assertEqual(root.findtext('PrimaryNTPServer'), 'primary.test')
        self.assertEqual(root.findtext('ActiveNTPServer'), 'primary.test')
        self.assertEqual(root.findtext('AppliedCorrectionMilliseconds'), '0.000')
        self.assertEqual(root.findtext('MeasuredOffsetMilliseconds'), '1250.000')
        self.assertEqual(datetime.fromisoformat(root.findtext('CurrentSystemTime')).utcoffset().total_seconds(), 0)

    def test_fallback_snapshot_distinguishes_configured_and_active_servers(self):
        self.query.side_effect = [NtpQueryError('timeout'), self.result]
        self.monitor.check_once()
        root = self.snapshot()
        self.assertEqual(root.findtext('PrimaryNTPServer'), 'primary.test')
        self.assertEqual(root.findtext('ActiveNTPServer'), 'secondary.test')
        self.assertEqual(root.findtext('ActiveServerRole'), 'secondary')
        self.assertEqual([a.attrib['status'] for a in root.findall('Attempts/Attempt')], ['failure', 'success'])

    def test_outage_replaces_previous_success_snapshot(self):
        self.monitor.check_once()
        self.query.side_effect = NtpQueryError('offline')
        self.monitor.check_once()
        root = self.snapshot()
        self.assertEqual(root.attrib['status'], 'failure')
        self.assertEqual(root.findtext('ActiveNTPServer'), '')
        self.assertEqual(root.findtext('IPAddress'), '')
        self.assertEqual(root.findtext('IPAddressSource'), 'unavailable')
        self.assertEqual(root.findtext('MeasuredOffsetMilliseconds'), '')
        self.assertEqual(root.findtext('AppliedCorrectionMilliseconds'), '0.000')
        self.assertEqual(root.findtext('SyncReason'), 'no_usable_server')
        self.assertEqual(len(root.findall('Attempts/Attempt')), 2)

    def test_snapshot_records_clock_failure(self):
        self.monitor.config['sync_system_clock'] = True
        self.set_clock.side_effect = ClockSyncError('permission denied')
        self.monitor.check_once()
        root = self.snapshot()
        self.assertEqual(root.attrib['status'], 'failure')
        self.assertEqual(root.findtext('SyncStatus'), 'failed')
        self.assertEqual(root.findtext('Message'), 'permission denied')
        self.assertEqual(root.findtext('AppliedCorrectionMilliseconds'), '0.000')

    def test_snapshot_applied_signed_correction(self):
        self.monitor.config['sync_system_clock'] = True
        self.result['offset_seconds'] = -1.25
        self.monitor.check_once()
        self.assertEqual(self.snapshot().findtext('AppliedCorrectionMilliseconds'), '-1250.000')
        self.assertEqual(self.snapshot().findtext('SyncStatus'), 'applied')

    def test_snapshot_replace_failure_preserves_previous_document(self):
        self.monitor.check_once()
        from pathlib import Path
        path = Path(self.monitor.xml_logger.current_status_path())
        before = path.read_bytes()
        import os
        replace = os.replace

        def fail_status(source, destination):
            if str(destination) == str(path):
                raise PermissionError('share unavailable')
            return replace(source, destination)

        with patch('ntp_client.xml_logger.os.replace', side_effect=fail_status):
            with self.assertRaises(PermissionError):
                self.monitor.check_once()
        self.assertEqual(path.read_bytes(), before)

    def test_primary_success_writes_xml_without_querying_secondary(self):
        self.monitor.check_once()
        self.query.assert_called_once_with('primary.test', timeout=5)
        self.set_clock.assert_not_called()
        entry = self.entries()[0]
        self.assertEqual(entry.findtext('Server'), 'primary.test')
        self.assertEqual(entry.findtext('OffsetMilliseconds'), '1250.000')
        self.assertEqual(entry.findtext('ClockSynced'), 'false')

    def test_primary_failure_falls_back_and_records_both_attempts(self):
        self.query.side_effect = [NtpQueryError('timeout'), self.result]
        self.monitor.check_once()
        self.assertEqual(self.query.call_args_list,
                         [call('primary.test', timeout=5), call('secondary.test', timeout=5)])
        self.assertEqual(self.events(), ['ConnectionLost', 'TimeCheck'])
        self.assertEqual(self.entries()[1].findtext('ServerRole'), 'secondary')

    def test_both_fail_then_recover(self):
        self.query.side_effect = [NtpQueryError('offline'), NtpQueryError('offline'), self.result]
        self.monitor.check_once()
        self.monitor.check_once()
        self.assertEqual(self.events(), ['ConnectionLost', 'ConnectionLost',
                                         'AllServersUnreachable', 'ConnectionRestored', 'TimeCheck'])
        self.assertEqual(self.entries()[2].attrib['status'], 'critical')

    def test_missing_optional_secondary(self):
        self.monitor.config['secondary_server'] = None
        self.query.side_effect = NtpQueryError('offline')
        self.monitor.check_once()
        self.query.assert_called_once()
        self.assertEqual(self.events(), ['ConnectionLost', 'AllServersUnreachable'])

    def test_consecutive_failure_counts(self):
        self.query.side_effect = NtpQueryError('offline')
        self.monitor.check_once()
        self.monitor.check_once()
        failures = [e for e in self.entries() if e.attrib['event'] == 'ConnectionLost']
        self.assertEqual([e.findtext('ConsecutiveFailures') for e in failures], ['1', '1', '2', '2'])

    def test_primary_recovery_reported_after_successful_fallback(self):
        self.query.side_effect = [NtpQueryError('offline'), self.result, self.result]
        self.monitor.check_once()
        self.monitor.check_once()
        restored = [e for e in self.entries() if e.attrib['event'] == 'ConnectionRestored']
        self.assertEqual([e.findtext('ServerRole') for e in restored], ['primary'])

    def test_secondary_recovery_is_reported_only_when_observed(self):
        self.query.side_effect = [NtpQueryError('offline'), NtpQueryError('offline'),
                                  self.result, NtpQueryError('offline'), self.result,
                                  NtpQueryError('offline'), self.result]
        for _ in range(4):
            self.monitor.check_once()
        restored = [e.findtext('ServerRole') for e in self.entries()
                    if e.attrib['event'] == 'ConnectionRestored']
        self.assertEqual(restored, ['primary', 'secondary'])

    def test_disabled_sync_never_sets_clock(self):
        self.assertEqual(self.monitor._maybe_sync_clock(100)["reason"], "disabled")
        self.set_clock.assert_not_called()

    def test_large_corrections_rejected_and_audited_in_both_directions(self):
        self.monitor.config['sync_system_clock'] = True
        for offset in (-5.01, 5.01):
            self.result['offset_seconds'] = offset
            self.monitor.check_once()
            root = self.snapshot()
            self.assertEqual(root.attrib['status'], 'failure')
            self.assertEqual(root.findtext('SyncReason'), 'correction_limit_exceeded')
            self.assertEqual(root.findtext('AppliedCorrectionMilliseconds'), '0.000')
            self.assertEqual(self.entries()[-1].findtext('SyncStatus'), 'failed')
        self.set_clock.assert_not_called()

    def test_configured_maximum_boundary_is_allowed(self):
        self.monitor.config.update(sync_system_clock=True, max_clock_correction_seconds=2)
        for offset in (-2, 2):
            self.assertEqual(self.monitor._maybe_sync_clock(offset)['status'], 'applied')
        self.assertEqual(self.monitor._maybe_sync_clock(2.01)['reason'], 'correction_limit_exceeded')
        self.assertEqual(self.set_clock.call_count, 2)

    def test_clock_change_after_query_blocks_correction(self):
        self.monitor.config['sync_system_clock'] = True
        self.result.update(t4=1000, monotonic_t4=10)
        with patch('ntp_client.monitor.datetime') as clock, \
                patch('ntp_client.monitor.time.monotonic', return_value=11):
            clock.now.return_value = datetime.fromtimestamp(1061, timezone.utc)
            self.monitor.check_once()
        self.assertEqual(self.snapshot().findtext('SyncReason'), 'local_clock_changed')
        self.set_clock.assert_not_called()

    def test_unchanged_clock_after_query_uses_current_time(self):
        self.monitor.config['sync_system_clock'] = True
        sample = dict(t4=1000, monotonic_t4=10)
        with patch('ntp_client.monitor.datetime') as clock, \
                patch('ntp_client.monitor.time.monotonic', return_value=12):
            clock.now.return_value = datetime.fromtimestamp(1002, timezone.utc)
            clock.fromtimestamp.side_effect = datetime.fromtimestamp
            result = self.monitor._maybe_sync_clock(1, sample)
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(self.set_clock.call_args[0][0].timestamp(), 1003)

    def test_threshold_skips_small_offsets_in_both_directions(self):
        self.monitor.config['sync_system_clock'] = True
        for offset in (-0.49, 0, 0.49):
            self.assertEqual(self.monitor._maybe_sync_clock(offset)["reason"], "below_threshold")
        self.set_clock.assert_not_called()

    def test_threshold_boundary_applies_signed_correction(self):
        self.monitor.config['sync_system_clock'] = True
        now = datetime(2026, 9, 25, tzinfo=timezone.utc)
        with patch('ntp_client.monitor.datetime') as clock:
            clock.now.return_value = now
            clock.fromtimestamp.side_effect = datetime.fromtimestamp
            for offset in (-0.5, 0.5):
                self.assertEqual(self.monitor._maybe_sync_clock(offset)["status"], "applied")
                self.assertEqual(self.set_clock.call_args[0][0].timestamp(), now.timestamp() + offset)

    def test_permission_failure_still_writes_measurement(self):
        self.monitor.config['sync_system_clock'] = True
        self.set_clock.side_effect = ClockSyncError('permission denied')
        self.monitor.check_once()
        self.assertEqual(self.entries()[0].findtext('ClockSynced'), 'false')
        self.assertEqual(self.entries()[0].findtext('OffsetMilliseconds'), '1250.000')
        self.logs.warning.assert_called_once()
        entry = self.entries()[0]
        self.assertEqual(entry.attrib['status'], 'failure')
        self.assertEqual(entry.findtext('SyncStatus'), 'failed')
        self.assertEqual(entry.findtext('AppliedCorrectionMilliseconds'), '0.000')
        self.assertIn('permission denied', entry.findtext('Message'))

    def test_applied_correction_audited_with_sign(self):
        self.monitor.config['sync_system_clock'] = True
        self.result['offset_seconds'] = -1.25
        self.monitor.check_once()
        entry = self.entries()[0]
        self.assertEqual(entry.findtext('SyncStatus'), 'applied')
        self.assertEqual(entry.findtext('SyncReason'), 'clock_set')
        self.assertEqual(entry.findtext('AppliedCorrectionMilliseconds'), '-1250.000')
        self.assertEqual(entry.findtext('ClockSynced'), 'true')

    def test_disabled_correction_audited_as_zero(self):
        self.monitor.check_once()
        entry = self.entries()[0]
        self.assertEqual(entry.findtext('SyncStatus'), 'skipped')
        self.assertEqual(entry.findtext('SyncReason'), 'disabled')
        self.assertEqual(entry.findtext('AppliedCorrectionMilliseconds'), '0.000')

    def test_below_threshold_audited_as_zero(self):
        self.monitor.config['sync_system_clock'] = True
        self.result['offset_seconds'] = 0.1
        self.monitor.check_once()
        self.assertEqual(self.entries()[0].findtext('SyncReason'), 'below_threshold')
        self.assertEqual(self.entries()[0].findtext('AppliedCorrectionMilliseconds'), '0.000')
        self.set_clock.assert_not_called()

    def test_unsynchronized_primary_falls_back_to_valid_secondary(self):
        self.monitor.config['sync_system_clock'] = True
        self.query.side_effect = [dict(self.result, unsynchronized=True), self.result]
        self.monitor.check_once()
        self.assertEqual(self.events(), ['ResponseRejected', 'TimeCheck'])
        self.assertEqual(self.entries()[0].findtext('SyncReason'), 'invalid_response')
        self.assertEqual(self.entries()[1].findtext('ServerRole'), 'secondary')
        self.set_clock.assert_called_once()

    def test_non_finite_offset_cannot_set_clock(self):
        self.monitor.config['sync_system_clock'] = True
        for offset in (float('nan'), float('inf'), float('-inf')):
            self.assertEqual(self.monitor._maybe_sync_clock(offset)['reason'], 'invalid_offset')
        self.set_clock.assert_not_called()

    def test_wire_rejection_through_fallback_and_xml(self):
        self.monitor.config['sync_system_clock'] = True
        self.query.side_effect = query_ntp_server
        with patch('ntp_client.ntp_query.socket.socket') as factory, \
                patch('ntp_client.ntp_query.time.monotonic', side_effect=[10, 10.5, 11, 11.5, 11.5]), \
                patch('ntp_client.monitor.datetime') as clock, \
                patch('ntp_client.ntp_query.time.time', side_effect=[1000, 1000.5, 1000, 1000.5]):
            clock.now.return_value = datetime.fromtimestamp(1000.5, timezone.utc)
            clock.fromtimestamp.side_effect = datetime.fromtimestamp
            factory.return_value.getsockname.return_value = ('192.0.2.10', 50000)
            factory.return_value.recv.side_effect = [packet(leap=3), packet()]
            self.monitor.check_once()
        self.assertEqual(self.events(), ['ResponseRejected', 'TimeCheck'])
        self.assertEqual(self.entries()[1].findtext('SyncStatus'), 'applied')
        self.assertEqual(self.entries()[1].findtext('AppliedCorrectionMilliseconds'), '1125.000')
        self.set_clock.assert_called_once()

    def test_all_rejected_produces_audit_without_clock_change(self):
        self.monitor.config['sync_system_clock'] = True
        self.result['unsynchronized'] = True
        self.monitor.check_once()
        self.assertEqual(self.events(), ['ResponseRejected', 'ResponseRejected', 'AllServersUnreachable'])
        for entry in self.entries():
            self.assertEqual(entry.findtext('SyncStatus'), 'skipped')
            self.assertEqual(entry.findtext('AppliedCorrectionMilliseconds'), '0.000')
        self.set_clock.assert_not_called()

    def test_unsynchronized_server_never_sets_clock(self):
        self.monitor.config['sync_system_clock'] = True
        self.result['unsynchronized'] = True
        self.monitor.check_once()
        self.set_clock.assert_not_called()

    def test_loop_recovers_from_cycle_exception_and_waits_remaining_interval(self):
        with patch.object(self.monitor, 'check_once', side_effect=[OSError('share offline'), None]) as check, \
                patch('ntp_client.monitor.time') as clock:
            clock.monotonic.side_effect = [1000, 1002, 1300, 1301]
            clock.sleep.side_effect = [None, KeyboardInterrupt]
            with self.assertRaises(KeyboardInterrupt):
                self.monitor.run_forever()
        self.assertEqual(check.call_count, 2)
        self.assertEqual(clock.sleep.call_args_list, [call(298), call(299)])
        self.logs.exception.assert_called_once()
