"""Check installer payload generation without native OS packaging tools."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntp_client.config import load_config


class PackagingTests(unittest.TestCase):
    def test_linux_payload_config_permissions_and_bundled_runtime(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('package_builder', root / 'scripts/build_linux_packages.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            bundle = source / 'dist/ntp-monitor'
            bundle.mkdir(parents=True)
            (bundle / 'ntp-monitor').write_text('fake executable')
            (bundle / 'ntp-monitor').chmod(0o755)
            (bundle / '_internal').mkdir()
            (bundle / '_internal/libpython.so').write_text('fake runtime')
            gui = source / 'dist/ntp-monitor-gui'
            gui.mkdir()
            (gui / 'ntp-monitor-gui').write_text('fake desktop executable')
            (source / 'config.json').write_text((root / 'config.json').read_text())
            (source / 'packaging/linux').mkdir(parents=True)
            (source / 'packaging/linux/ntp-monitor.service').write_text(
                (root / 'packaging/linux/ntp-monitor.service').read_text())
            for filename in ('ntp-monitor-gui', 'ntp-monitor.desktop'):
                (source / 'packaging/linux' / filename).write_text((root / 'packaging/linux' / filename).read_text())
            (source / 'schemas').mkdir()
            target = Path(temporary) / 'payload'
            with patch.object(builder, 'ROOT', source):
                builder.stage(target)
            config = target / 'etc/ntp-monitor/config.json'
            self.assertEqual(load_config(config)['log_directory'], os.path.normpath('/var/log/ntp-monitor'))
            self.assertFalse(json.loads(config.read_text())['sync_system_clock'])
            if os.name == 'posix':
                self.assertEqual(config.stat().st_mode & 0o777, 0o640)
                self.assertEqual(config.parent.stat().st_mode & 0o777, 0o750)
            self.assertTrue((target / 'opt/ntp-monitor/_internal/libpython.so').is_file())
            if os.name == 'posix':
                self.assertTrue((target / 'opt/ntp-monitor/ntp-monitor').stat().st_mode & 0o100)

    def test_frozen_cli_uses_external_os_config_path(self):
        import runpy
        root = Path(__file__).resolve().parents[1]
        for platform, expected in [('linux', '/etc/ntp-monitor/config.json'),
                                    ('win32', str(Path('test-program-data') / 'NTPClientMonitor/config.json'))]:
            with self.subTest(platform=platform), patch('sys.frozen', True, create=True), \
                    patch('sys.platform', platform), patch.dict('os.environ', {'ProgramData': 'test-program-data'}):
                namespace = runpy.run_path(str(root / 'main.py'), run_name='package_path_test')
                self.assertEqual(namespace['DEFAULT_CONFIG_PATH'], expected)
