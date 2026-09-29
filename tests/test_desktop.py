import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ntp_client.config import load_config
from ntp_client.desktop import read_status, save_config, service_command, read_history
from ntp_client.xml_logger import XmlLogger


class DesktopTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'config.json'
        self.raw = dict(primary_server='time.test', log_directory='./logs', workstation_name='TEST')
        self.path.write_text(json.dumps(self.raw))
        self.config = load_config(self.path)
        self.logger = XmlLogger(self.config['log_directory'], 'TEST')

    def snapshot(self):
        self.logger.write_status('time.test', None, [], 'success', 'time.test', 'primary',
                                 '192.0.2.1', 10, dict(status='skipped', reason='disabled', applied_ms=0))

    def test_save_invalid_settings_preserves_original(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            save_config(self.path, dict(self.raw, check_interval_minutes=16))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob('.config-*')), [])

    def test_save_valid_settings_preserves_path_and_permissions(self):
        self.path.chmod(0o640)
        save_config(self.path, dict(self.raw, check_interval_minutes=10))
        self.assertEqual(load_config(self.path)['check_interval_seconds'], 600)
        self.assertEqual(json.loads(self.path.read_text())['log_directory'], './logs')
        if os.name == 'posix':
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)

    def test_snapshot_age_and_staleness(self):
        self.snapshot()
        current = read_status(self.config)
        self.assertFalse(current['stale'])
        self.assertEqual(current['SyncStatus'], 'skipped')
        later = read_status(self.config, datetime.now(timezone.utc) + timedelta(minutes=10))
        self.assertTrue(later['stale'])
        self.assertEqual(later['next_seconds'], 0)

    def test_corrupt_xml_reported_as_unavailable(self):
        Path(self.logger.current_status_path()).write_text('<broken')
        with self.assertRaisesRegex(ValueError, 'Unreadable XML'):
            read_status(self.config)

    def test_last_sync_is_applied_not_last_measurement(self):
        self.logger.log_entry('TimeCheck', 'success', sync_status='applied', applied_correction_ms=2)
        self.logger.log_entry('TimeCheck', 'success', sync_status='skipped', applied_correction_ms=0)
        last, entries = read_history(self.config)
        self.assertEqual(last.findtext('AppliedCorrectionMilliseconds'), '2.000')
        self.assertEqual(len(entries), 2)

    def test_service_actions_use_fixed_commands(self):
        self.assertIn('Restart-Service NTPClientMonitor', service_command('restart', 'Windows')[-1])
        with patch('ntp_client.desktop.os.geteuid', return_value=1000, create=True):
            self.assertEqual(service_command('restart', 'Linux'), ['pkexec', 'systemctl', 'restart', 'ntp-monitor.service'])
        with self.assertRaises(ValueError):
            service_command('arbitrary command', 'Windows')

    def test_save_creates_missing_settings(self):
        new = self.path.parent / 'new' / 'config.json'
        save_config(new, dict(self.raw, setup_complete=True))
        self.assertTrue(load_config(new)['setup_complete'])

    def test_repair_keeps_original_backup(self):
        self.path.write_text('{broken')
        save_config(self.path, dict(self.raw, setup_complete=True))
        self.assertEqual(Path(str(self.path) + '.previous').read_text(), '{broken')
        self.assertEqual(load_config(self.path)['primary_server'], 'time.test')

    def test_start_verifies_running_and_enables_boot(self):
        from ntp_client.desktop import start_configured_service
        with patch('ntp_client.desktop.control_service', side_effect=['', '', 'active']) as control, patch('ntp_client.desktop.time.sleep'):
            self.assertEqual(start_configured_service(), 'active')
            self.assertEqual([c.args[0] for c in control.call_args_list], ['enable', 'restart', 'status'])

    def test_failed_start_is_not_reported_as_success(self):
        from ntp_client.desktop import start_configured_service
        with patch('ntp_client.desktop.control_service', side_effect=['', '', 'failed']), patch('ntp_client.desktop.time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'did not stay running'):
                start_configured_service()
