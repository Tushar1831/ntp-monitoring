"""Exercise first-run GUI cancel/save/repair without an installed service."""
import json
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui import MonitorWindow
from ntp_client.config import load_config


def pump(root, duration=.3):
    end = time.monotonic() + duration
    while time.monotonic() < end:
        root.update()
        time.sleep(.01)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


with tempfile.TemporaryDirectory() as temporary:
    for broken in (False, True):
        path = Path(temporary) / ('broken.json' if broken else 'config.json')
        path.write_text('{broken' if broken else json.dumps(dict(primary_server='time.test', log_directory='./logs', setup_complete=False)))
        root = tk.Tk()
        with patch.object(MonitorWindow, 'refresh'), patch('gui.start_configured_service', return_value='active') as start:
            window = MonitorWindow(root, path)
            window.controls_service = True
            pump(root)
            dialog = window.settings_dialog
            assert dialog.winfo_exists()
            assert not start.called
            # Cancelling first-run setup must not contact a server/start the service.
            dialog.destroy()
            assert window.needs_setup
            window.settings(first_run=True)
            dialog = window.settings_dialog
            entries = [w for w in descendants(dialog) if isinstance(w, ttk.Entry) and not isinstance(w, ttk.Combobox)]
            entries[0].delete(0, 'end')
            entries[0].insert(0, 'time.test')
            maximum = next(w for w in entries if int(w.grid_info()['row']) == 5)
            maximum.delete(0, 'end')
            maximum.insert(0, '2')
            buttons = [w for w in descendants(dialog) if isinstance(w, ttk.Button)]
            next(w for w in buttons if w.cget('text') == 'Save and start').invoke()
            pump(root)
            assert load_config(path)['setup_complete'] is True
            assert load_config(path)['max_clock_correction_seconds'] == 2
            start.assert_called_once_with()
            assert window.service == 'active'
            if broken:
                assert Path(str(path) + '.previous').read_text() == '{broken'
            window.close()
print('First-run cancel, Save and start, and invalid-config repair passed')
