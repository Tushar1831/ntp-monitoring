"""Render a deterministic example and exercise settings without touching a service.

Run with a display or xvfb-run. Optional argument saves a screenshot via ImageMagick.
"""
from pathlib import Path
import json
import sys
import tempfile
import tkinter as tk
from unittest.mock import patch
from datetime import datetime, timezone
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui import MonitorWindow
from ntp_client.config import load_config
from ntp_client.xml_logger import XmlLogger
from ntp_client.desktop import read_status, read_history

with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'config.json'
    path.write_text(json.dumps(dict(primary_server='ntp-primary.internal', secondary_server='ntp-backup.internal',
                                   log_directory='./logs', workstation_name='WORKSTATION-042', sync_system_clock=True)))
    config = load_config(path)
    logger = XmlLogger(config['log_directory'], 'WORKSTATION-042')
    logger.log_entry('TimeCheck', 'success', server='ntp-primary.internal', sync_status='applied', applied_correction_ms=-12.5)
    logger.write_status('ntp-primary.internal', 'ntp-backup.internal',
                        [dict(server='ntp-primary.internal', role='primary', status='success', reason='usable_response', message='')],
                        'success', 'ntp-primary.internal', 'primary', '192.0.2.42', -12.5,
                        dict(status='applied', reason='clock_set', applied_ms=-12.5))
    root = tk.Tk()
    with patch.object(MonitorWindow, 'refresh'), patch('gui.control_service') as service:
        window = MonitorWindow(root, path)
        window.controls_service = True
        last, history = read_history(config)
        window.render((config, 'Running', read_status(config), last, history))
        root.update()
        assert len(window.servers.get_children()) == 2
        assert 'Clock correction applied' in window.banner.get()
        if len(sys.argv) > 1:
            subprocess.run(['import', '-window', str(root.winfo_id()), sys.argv[1]], check=True)
        window.settings()
        root.update()
        dialogs = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
        assert len(dialogs) == 1
        dialogs[0].destroy()
        window.close()
        service.assert_not_called()
print('Desktop render, settings dialog, and independent close passed')
