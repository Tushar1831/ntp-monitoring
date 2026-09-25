#!/usr/bin/env python3
"""Small native settings/status window; service remains independent."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import queue
import os
import platform
import tkinter as tk
from tkinter import ttk, messagebox

from main import DEFAULT_CONFIG_PATH
from ntp_client.config import load_config
from ntp_client.desktop import control_service, read_status, read_history, save_config


class MonitorWindow:
    def __init__(self, root, config_path):
        self.root, self.path = root, Path(config_path)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.messages = queue.Queue()
        self.busy = False
        self.config = None
        self.service = 'Unknown'
        installed = (Path(os.environ.get('ProgramData', r'C:\ProgramData')) / 'NTPClientMonitor/config.json'
                     if platform.system() == 'Windows' else Path('/etc/ntp-monitor/config.json'))
        self.controls_service = platform.system() in ('Windows', 'Linux') and self.path.resolve() == installed.resolve()
        self.poll_count = 0
        root.title('Network Time — NTP Client Monitor')
        root.geometry('920x650')
        root.minsize(800, 580)
        root.protocol('WM_DELETE_WINDOW', self.close)
        frame = ttk.Frame(root, padding=18)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Network Time', font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Workstation & server time synchronization').pack(anchor='w', pady=(0, 12))
        self.summary = {}
        facts = ttk.Frame(frame)
        facts.pack(fill='x')
        for row, (key, label) in enumerate([('time', 'System time'), ('host', 'Endpoint'),
                ('attempt', 'Last attempt (UTC)'), ('sync', 'Last applied correction'), ('next', 'Next attempt'),
                ('service', 'Background service'), ('mode', 'Operating mode')]):
            ttk.Label(facts, text=label + ':', width=24).grid(row=row, column=0, sticky='w', pady=2)
            value = tk.StringVar(value='—')
            ttk.Label(facts, textvariable=value).grid(row=row, column=1, sticky='w')
            self.summary[key] = value
        self.banner = tk.StringVar(value='Reading service status…')
        ttk.Label(frame, textvariable=self.banner, wraplength=860, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=12)
        tabs = ttk.Notebook(frame)
        tabs.pack(fill='both', expand=True)
        servers = ttk.Frame(tabs, padding=8)
        tabs.add(servers, text='Time servers')
        self.servers = self.table(servers, ('Role', 'Server', 'Status', 'Offset (ms)', 'Last error'), (80, 210, 120, 110, 270))
        history = ttk.Frame(tabs, padding=8)
        tabs.add(history, text='Recent activity')
        self.history = self.table(history, ('Time (UTC)', 'Event', 'Status', 'Details'), (200, 160, 90, 330))
        output = ttk.Frame(tabs, padding=12)
        tabs.add(output, text='XML & diagnostics')
        self.output = tk.StringVar(value='')
        ttk.Label(output, textvariable=self.output, wraplength=830, justify='left').pack(anchor='w')
        ttk.Label(output, text='Secure/authenticated NTP (NTS): not implemented.\nClient only — this application does not serve time.').pack(anchor='w', pady=12)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=(14, 0))
        self.actions = []
        for text, command in [('Check now', lambda: self.action('restart')),
                              ('Start', lambda: self.action('start')), ('Stop', lambda: self.action('stop')),
                              ('Settings…', self.settings), ('About', self.about)]:
            button = ttk.Button(buttons, text=text, command=command)
            button.pack(side='left', padx=(0, 8))
            self.actions.append(button)
        ttk.Button(buttons, text='Close', command=self.close).pack(side='right')
        self.summary['time'].set(datetime.now().astimezone().strftime('%d %b %Y  %H:%M:%S %Z'))
        self.refresh()
        self.tick()

    def table(self, parent, columns, widths):
        table = ttk.Treeview(parent, columns=columns, show='headings', height=5)
        for name, width in zip(columns, widths):
            table.heading(name, text=name)
            table.column(name, width=width, minwidth=60)
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        table.pack(fill='both', expand=True)
        return table

    def submit(self, work, done):
        if self.busy:
            return
        self.busy = True
        for button in self.actions:
            button.configure(state='disabled')
        future = self.executor.submit(work)
        future.add_done_callback(lambda result: self.messages.put((result, done)))

    def refresh(self):
        def read():
            config = load_config(self.path)
            try:
                service = control_service('status') if self.controls_service else 'Not attached — viewing a configuration file'
            except (OSError, RuntimeError, TimeoutError) as error:
                service = 'Unavailable: ' + str(error)
            try:
                status = read_status(config)
            except (OSError, ValueError, KeyError) as error:
                status = {'error': str(error)}
            try:
                last, history = read_history(config)
            except (OSError, ValueError):
                last, history = None, []
            return config, service, status, last, history
        self.submit(read, self.render)

    def render(self, data):
        self.config, self.service, status, last, history = data
        self.summary['service'].set({'active': 'Running', 'inactive': 'Stopped', 'failed': 'Failed'}.get(self.service, self.service))
        self.summary['mode'].set('Synchronize system clock' if self.config['sync_system_clock'] else 'Monitor only — clock changes disabled')
        self.summary['sync'].set((last.get('timestamp') + '  ' + last.findtext('AppliedCorrectionMilliseconds', '') + ' ms') if last is not None else 'Not recorded in current history')
        self.servers.delete(*self.servers.get_children())
        attempts = {a['ServerRole']: a for a in status.get('attempts', [])}
        for role in ('primary', 'secondary'):
            server = self.config.get(role + '_server')
            attempt = attempts.get(role, {})
            used = status.get('ActiveServerRole') == role
            self.servers.insert('', 'end', values=(role.title(), server or 'Not configured',
                ('Unavailable' if 'error' in status else {'success': 'Good', 'failure': 'Failed'}.get(attempt.get('status'), 'Not used')),
                status.get('MeasuredOffsetMilliseconds', '—') if used else '—', attempt.get('Message', '')))
        self.history.delete(*self.history.get_children())
        for entry in reversed(history):
            self.history.insert('', 'end', values=(entry.get('timestamp'), entry.get('event'), entry.get('status'),
                entry.findtext('Message') or entry.findtext('SyncReason') or entry.findtext('Server') or ''))
        if 'error' in status:
            self.banner.set('Status unavailable: ' + status['error'])
            for key in ('host', 'attempt', 'next'):
                self.summary[key].set('Unavailable')
        else:
            self.summary['host'].set(status.get('WorkstationName', '') + '  |  ' + (status.get('IPAddress') or 'IP unavailable'))
            self.summary['attempt'].set(status['CurrentSystemTime'])
            running = self.service in ('active', 'Running')
            self.summary['next'].set('Approximately %dm %02ds' % divmod(status['next_seconds'], 60) if running and not status['stale'] else 'Unavailable — service stopped or status stale')
            labels = {'applied': 'Clock correction applied', 'skipped': 'Clock correction skipped', 'failed': 'Clock correction failed'}
            reasons = {'clock_set': 'System clock updated', 'disabled': 'Monitoring only',
                       'below_threshold': 'Offset is below the configured threshold',
                       'clock_set_failed': 'The operating system rejected the adjustment',
                       'no_usable_server': 'Neither configured server supplied usable time',
                       'invalid_response': 'Server response rejected', 'query_failed': 'Server could not be reached'}
            text = labels.get(status.get('SyncStatus'), 'Unknown result') + ' — ' + reasons.get(status.get('SyncReason'), status.get('SyncReason', ''))
            if status.get('Message'):
                text += ' — ' + status['Message']
            if status['stale']:
                text = 'STALE STATUS — ' + text
            if not running:
                text = 'SERVICE NOT RUNNING — ' + text
            self.banner.set(text)
        self.output.set('Configuration: ' + str(self.path) + '\n\nXML directory: ' + self.config['log_directory'] +
                        '\nCurrent status: <host>_ntpstatus.xml\nHistory: <host>_ntplog[date].xml' +
                        '\nRotation: ' + self.config['log_rotation'] + '\nEntry limit: ' + str(self.config['max_log_entries_per_file']) +
                        '\n\nOperational logs: Windows service_debug.log in the log directory; Linux journalctl -u ntp-monitor.')

    def action(self, action):
        if not self.controls_service:
            messagebox.showinfo('Service controls', 'Open the installed service configuration to control its service.', parent=self.root)
            return
        # Restart invokes the service's normal first cycle: no competing writer.
        if action == 'restart' and not messagebox.askokcancel('Check now', 'Restart the background service to perform a new check immediately?', parent=self.root):
            return
        self.submit(lambda: control_service(action), lambda _: self.banner.set('Service command completed. Refreshing status…'))

    def settings(self):
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            messagebox.showerror('Settings unavailable', str(error), parent=self.root)
            return
        dialog = tk.Toplevel(self.root)
        dialog.title('Network Time settings')
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill='both', expand=True)
        fields = [('primary_server', 'Primary NTP server'), ('secondary_server', 'Fallback NTP server'),
                  ('check_interval_minutes', 'Interval (1–15 minutes)'), ('timeout_seconds', 'Timeout (seconds)'),
                  ('resync_threshold_seconds', 'Correction threshold (seconds; blank = none)'),
                  ('log_directory', 'XML / log directory'), ('log_rotation', 'Rotation (none / daily)'),
                  ('max_log_entries_per_file', 'History entry limit (blank = unlimited)'),
                  ('workstation_name', 'Host override (blank = automatic)')]
        variables = {}
        for row, (key, label) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky='w', pady=5)
            value = raw.get(key, self.config.get(key) if self.config else '')
            if key == 'check_interval_minutes':
                value = raw.get(key, raw.get('check_interval_seconds', 300) / 60)
            variables[key] = tk.StringVar(value='' if value is None else str(value))
            if key == 'log_rotation':
                entry = ttk.Combobox(body, textvariable=variables[key], values=('none', 'daily'), state='readonly', width=35)
            else:
                entry = ttk.Entry(body, textvariable=variables[key], width=38)
            entry.grid(row=row, column=1, sticky='ew', padx=(15, 0))
        sync = tk.BooleanVar(value=raw.get('sync_system_clock', False))
        ttk.Checkbutton(body, text='Adjust system clock (requires service privileges)', variable=sync).grid(row=9, columnspan=2, sticky='w', pady=8)
        ttk.Label(body, text='Saving requires administrator/root access. Restart the service to apply changes.').grid(row=10, columnspan=2, sticky='w')

        def save():
            try:
                values = dict(raw)
                values.pop('check_interval_seconds', None)
                for key, _ in fields:
                    value = variables[key].get().strip()
                    if key in ('check_interval_minutes', 'max_log_entries_per_file'):
                        number = float(value) if value else None
                        if number is not None and not number.is_integer():
                            raise ValueError(key + ': enter a whole number')
                        value = int(number) if number is not None else None
                    elif key in ('timeout_seconds', 'resync_threshold_seconds'):
                        value = float(value) if value else None
                    elif key in ('secondary_server', 'workstation_name') and not value:
                        value = None
                    values[key] = value
                values['sync_system_clock'] = sync.get()
                save_config(self.path, values)
            except (OSError, ValueError, OverflowError) as error:
                messagebox.showerror('Settings not saved', str(error), parent=dialog)
                return
            dialog.destroy()
            if self.controls_service and messagebox.askyesno('Settings saved', 'Restart the service now to apply these settings?', parent=self.root):
                self.submit(lambda: control_service('restart'), lambda _: self.refresh())
        ttk.Button(body, text='Save', command=save).grid(row=11, column=1, sticky='e', pady=(12, 0))
        ttk.Button(body, text='Cancel', command=dialog.destroy).grid(row=11, column=0, sticky='w', pady=(12, 0))

    def about(self):
        messagebox.showinfo('About Network Time', 'NTP Client Monitor\nWindows and Linux background service\nPrimary/fallback NTP, clock correction, XML audit and configurable retention.\n\nClosing this window leaves the service running.\nNTS and time-server hosting are not implemented.', parent=self.root)

    def tick(self):
        self.summary['time'].set(datetime.now().astimezone().strftime('%d %b %Y  %H:%M:%S %Z'))
        try:
            future, done = self.messages.get_nowait()
            self.busy = False
            for index, button in enumerate(self.actions):
                button.configure(state='normal' if index >= 3 or self.controls_service else 'disabled')
            try:
                done(future.result())
            except Exception as error:
                self.banner.set(str(error))
        except queue.Empty:
            pass
        self.poll_count += 1
        if not self.busy and self.poll_count >= 15:
            self.poll_count = 0
            self.refresh()
        self.root.after(200, self.tick)

    def close(self):
        self.executor.shutdown(wait=False)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description='NTP Client Monitor desktop window')
    parser.add_argument('--config', default=DEFAULT_CONFIG_PATH)
    args = parser.parse_args()
    root = tk.Tk()
    MonitorWindow(root, args.config)
    root.mainloop()


if __name__ == '__main__':
    main()
