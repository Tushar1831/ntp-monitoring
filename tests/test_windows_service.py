"""Portable wrapper test with simulated pywin32; not a Windows SCM test."""
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class WindowsServiceTests(unittest.TestCase):
    def test_fresh_start_creates_log_directory_before_opening_debug_log(self):
        modules = {name: types.ModuleType(name) for name in
                   ('servicemanager', 'win32event', 'win32service', 'win32serviceutil')}
        modules['win32serviceutil'].ServiceFramework = object
        modules['servicemanager'].LogMsg = Mock()
        modules['servicemanager'].LogErrorMsg = Mock()
        modules['servicemanager'].EVENTLOG_INFORMATION_TYPE = 1
        modules['servicemanager'].PYS_SERVICE_STARTED = 1
        source = Path(__file__).resolve().parents[1] / 'install' / 'windows_service.py'
        spec = importlib.util.spec_from_file_location('service_under_test', str(source))
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', modules):
            spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            logs = Path(directory) / 'new-logs'
            config = Path(directory) / 'config.json'
            config.write_text(json.dumps({'primary_server': 'primary.test',
                                           'log_directory': str(logs)}), encoding='utf-8')
            module.CONFIG_PATH = str(config)
            service = object.__new__(module.NtpMonitorService)
            service.running = False  # Exercise startup only, with no polling.

            def open_debug_log(**kwargs):
                # Deterministic even if the test runner already has logging handlers.
                with open(kwargs['filename'], 'a', encoding='utf-8'):
                    pass

            with patch.object(module.logging, 'basicConfig', side_effect=open_debug_log):
                service.SvcDoRun()
            self.assertTrue((logs / 'service_debug.log').is_file())
            # Both entry points must reject the same invalid settings before startup.
            config.write_text(json.dumps({'primary_server': 'primary.test',
                                           'log_directory': str(logs),
                                           'sync_system_clock': 'false'}), encoding='utf-8')
            modules['servicemanager'].LogMsg.reset_mock()
            with self.assertRaisesRegex(ValueError, 'sync_system_clock'):
                service.SvcDoRun()
            modules['servicemanager'].LogErrorMsg.assert_called_once()
            modules['servicemanager'].LogMsg.assert_not_called()
