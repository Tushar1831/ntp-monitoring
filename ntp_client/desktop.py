"""Desktop adapter. Reads service-owned XML; never runs a second polling loop."""
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from .config import load_config


def service_command(action, system=None):
    system = system or platform.system()
    if action not in ('status', 'start', 'stop', 'restart'):
        raise ValueError('Unsupported service action')
    if system == 'Windows':
        verbs = {'status': '(Get-Service NTPClientMonitor).Status.ToString()',
                 'start': 'Start-Service NTPClientMonitor', 'stop': 'Stop-Service NTPClientMonitor',
                 'restart': 'Restart-Service NTPClientMonitor'}
        return ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                "$ErrorActionPreference='Stop'; " + verbs[action]]
    if system == 'Linux':
        command = ['systemctl', 'is-active' if action == 'status' else action, 'ntp-monitor.service']
        if action != 'status' and os.geteuid() != 0:
            command.insert(0, 'pkexec')
        return command
    raise RuntimeError('Service controls are available on Windows and Linux only')


def control_service(action):
    result = subprocess.run(service_command(action), capture_output=True, text=True, timeout=60,
                            **({'creationflags': 0x08000000} if os.name == 'nt' else {}))
    if action == 'status' and result.stdout.strip() in ('active', 'inactive', 'failed', 'Running', 'Stopped'):
        return result.stdout.strip()
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Service command failed')
    return result.stdout.strip()


def save_config(path, values):
    """Validate before replacing; preserve permissions and leave bad edits unapplied."""
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.config-', suffix='.json', dir=str(path.parent))
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(values, stream, indent=2)
            stream.write('\n')
        load_config(temporary)
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_xml(path):
    try:
        return ET.parse(path).getroot()
    except ET.ParseError as error:
        raise ValueError('Unreadable XML: ' + str(error)) from error


def read_status(config, now=None):
    now = now or datetime.now(timezone.utc)
    host = config.get('workstation_name') or socket.gethostname()
    path = Path(config['log_directory']) / (host + '_ntpstatus.xml')
    root = _read_xml(path)
    if root.tag != 'NTPClientStatus' or root.get('schemaVersion') != '1.0':
        raise ValueError('Unsupported status XML format')
    values = {child.tag: child.text or '' for child in root if child.tag != 'Attempts'}
    report_time = datetime.fromisoformat(values['CurrentSystemTime'])
    if report_time.tzinfo is None:
        raise ValueError('Status timestamp has no time zone')
    age = (now - report_time).total_seconds()
    interval = config['check_interval_seconds']
    values['stale'] = age > interval + 2 * config['timeout_seconds'] + 15 or age < -5
    values['age'] = age
    values['next_seconds'] = max(0, int(interval - age))
    values['status'] = root.get('status')
    values['attempts'] = [{**{e.tag: e.text or '' for e in a}, 'status': a.get('status')}
                          for a in root.findall('Attempts/Attempt')]
    return values


def read_history(config):
    host = config.get('workstation_name') or socket.gethostname()
    suffix = '_' + datetime.now().strftime('%Y%m%d') if config['log_rotation'] == 'daily' else ''
    path = Path(config['log_directory']) / (host + '_ntplog' + suffix + '.xml')
    root = _read_xml(path)
    entries = root.findall('Entry')
    last_sync = next((e for e in reversed(entries) if e.findtext('SyncStatus') == 'applied'), None)
    return last_sync, entries[-30:]
