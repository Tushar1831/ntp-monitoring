import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class ConfigTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'config.json'
        self.config = {'primary_server': 'primary.test', 'log_directory': './logs'}

    def load(self):
        self.path.write_text(json.dumps(self.config), encoding='utf-8')
        return main.load_config(str(self.path))

    def test_relative_logs_resolve_from_config_directory(self):
        self.assertEqual(self.load()['log_directory'], str(self.path.parent / 'logs'))

    def test_absolute_log_path_preserved(self):
        self.config['log_directory'] = str(self.path.parent / 'absolute')
        self.assertEqual(self.load()['log_directory'], self.config['log_directory'])

    def test_required_fields(self):
        for field in ('primary_server', 'log_directory'):
            with self.subTest(field=field):
                original = self.config.pop(field)
                with self.assertRaisesRegex(ValueError, field):
                    self.load()
                self.config[field] = original

    def test_malformed_json(self):
        self.path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(json.JSONDecodeError):
            main.load_config(str(self.path))

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            main.load_config(str(self.path))

    def test_interval_boundaries_in_existing_seconds_format(self):
        for seconds in (60, 900):
            self.config['check_interval_seconds'] = seconds
            self.assertEqual(self.load()['check_interval_seconds'], seconds)

    def test_reject_interval_below_brd_minimum(self):
        self.config['check_interval_seconds'] = 59
        with self.assertRaises(ValueError):
            self.load()

    def test_reject_interval_above_brd_maximum(self):
        self.config['check_interval_seconds'] = 901
        with self.assertRaises(ValueError):
            self.load()

    def test_reject_string_interval(self):
        self.config['check_interval_seconds'] = 'five'
        with self.assertRaises(ValueError):
            self.load()

    def test_cli_once_runs_one_cycle(self):
        self.load()
        with patch('sys.argv', ['main.py', '--config', str(self.path), '--once']), \
                patch('main.setup_logging'), patch('main.NtpMonitor') as monitor:
            main.main()
        monitor.return_value.check_once.assert_called_once_with()
        monitor.return_value.run_forever.assert_not_called()

    def test_check_config_does_not_initialize_monitor(self):
        self.load()
        with patch('sys.argv', ['main.py', '--config', str(self.path), '--check-config']), \
                patch('main.setup_logging'), patch('main.NtpMonitor') as monitor:
            main.main()
        monitor.assert_not_called()

    def test_cli_bad_config_exits_one(self):
        with patch('sys.argv', ['main.py', '--config', str(self.path)]), \
                patch('main.setup_logging'), patch('main.NtpMonitor') as monitor, \
                self.assertLogs('ntp_monitor', level='ERROR'), \
                self.assertRaises(SystemExit) as error:
            main.main()
        self.assertEqual(error.exception.code, 1)
        monitor.assert_not_called()

    def test_minutes_normalized_and_defaults_applied(self):
        for minutes in (1, 5, 15):
            self.config['check_interval_minutes'] = minutes
            loaded = self.load()
            self.assertEqual(loaded['check_interval_seconds'], minutes * 60)
            self.assertNotIn('check_interval_minutes', loaded)
            self.assertIs(loaded['sync_system_clock'], False)
            self.assertEqual(loaded['max_log_entries_per_file'], 20000)

    def test_reject_invalid_values(self):
        cases = {
            'check_interval_minutes': [0, 16, 1.5, True, '5', None],
            'check_interval_seconds': [True, 60.5, None],
            'timeout_seconds': [0, -1, 301, True, '5', None, float('nan'), float('inf')],
            'resync_threshold_seconds': [-1, True, '0.5', float('nan'), float('inf')],
            'sync_system_clock': ['false', 0, 1, None],
            'max_log_entries_per_file': [0, -1, 2.5, True, '10'],
            'log_rotation': ['weekly', None, [], {}],
            'primary_server': ['', ' bad.test', 'https://time.test', 'a..test', '999.1.1.1', '::1', 123],
            'secondary_server': ['', False, 'time.test:123'],
            'log_directory': ['', '  ', None, [], 'bad\x00path', 'bad\npath'],
            'workstation_name': ['', '../host', 'a/b', 'a\\b', 'a:b', True],
        }
        original = dict(self.config)
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    self.config = dict(original, **{key: value})
                    with self.assertRaisesRegex(ValueError, key):
                        self.load()

    def test_ambiguous_units_and_unknown_keys_rejected(self):
        self.config.update(check_interval_minutes=5, check_interval_seconds=300)
        with self.assertRaisesRegex(ValueError, 'only one'):
            self.load()
        self.config.pop('check_interval_seconds')
        self.config['sync_system_clok'] = True
        with self.assertRaisesRegex(ValueError, 'sync_system_clok'):
            self.load()

    def test_non_object_and_duplicate_keys_rejected(self):
        for text in ('[]', 'null', '42', '{"primary_server":"a","primary_server":"b"}'):
            with self.subTest(text=text):
                self.path.write_text(text, encoding='utf-8')
                with self.assertRaises(ValueError):
                    main.load_config(str(self.path))

    def test_valid_optional_values(self):
        self.config.update(secondary_server=None, resync_threshold_seconds=None,
                           max_log_entries_per_file=None, workstation_name='HOST_01.example',
                           primary_server='192.0.2.1', timeout_seconds=0.5)
        self.assertIsNone(self.load()['max_log_entries_per_file'])

    def test_reload_reads_new_configuration(self):
        self.config['check_interval_minutes'] = 1
        self.assertEqual(self.load()['check_interval_seconds'], 60)
        self.config['check_interval_minutes'] = 15
        self.assertEqual(self.load()['check_interval_seconds'], 900)

    def test_cli_unwritable_log_directory_exits_cleanly(self):
        self.load()
        with patch('sys.argv', ['main.py', '--config', str(self.path)]), \
                patch('main.setup_logging'), \
                patch('main.NtpMonitor', side_effect=PermissionError('denied')), \
                self.assertLogs('ntp_monitor', level='ERROR'), \
                self.assertRaises(SystemExit) as error:
            main.main()
        self.assertEqual(error.exception.code, 1)

    def test_pending_setup_blocks_monitor_before_files_or_network(self):
        from ntp_client.monitor import NtpMonitor
        self.config['setup_complete'] = False
        config = self.load()
        with patch('ntp_client.monitor.XmlLogger') as logger:
            with self.assertRaisesRegex(ValueError, 'Complete setup'):
                NtpMonitor(config)
            logger.assert_not_called()

    def test_require_setup_cli_reports_pending(self):
        self.config['setup_complete'] = False
        self.load()
        with patch('sys.argv', ['main.py', '--config', str(self.path), '--check-config', '--require-setup']), patch('main.setup_logging'), self.assertLogs('ntp_monitor', level='ERROR'), self.assertRaises(SystemExit) as error:
            main.main()
        self.assertEqual(error.exception.code, 2)

    def test_windows_utf8_bom_configuration(self):
        self.path.write_text(json.dumps(self.config), encoding='utf-8-sig')
        self.assertEqual(main.load_config(self.path)['primary_server'], 'primary.test')

    def test_setup_flag_must_be_boolean(self):
        self.config['setup_complete'] = 'true'
        with self.assertRaisesRegex(ValueError, 'setup_complete'):
            self.load()
