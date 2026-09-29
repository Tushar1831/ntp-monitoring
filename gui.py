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
from tkinter import ttk, messagebox, filedialog

from main import DEFAULT_CONFIG_PATH
from ntp_client.config import load_config, DEFAULTS, KEYS
from ntp_client.desktop import control_service, read_status, read_history, save_config, start_configured_service, diagnostics


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
        self.settings_dialog = None
        self.timer = None
        self.setup_timer = None
        try:
            initial = load_config(self.path)
            self.needs_setup = not initial['setup_complete']
        except (OSError, ValueError):
            self.needs_setup = True
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
        ttk.Button(output, text='View diagnostic details…', command=self.show_diagnostics).pack(anchor='w', pady=8)
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
        if self.needs_setup:
            self.banner.set('Welcome — complete setup to start monitoring.')
            self.summary['service'].set('Waiting for setup')
            self.setup_timer = self.root.after(100, lambda: self.settings(first_run=True))
        else:
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

    def submit(self, work, done, on_error=None):
        if self.busy:
            return
        self.busy = True
        for button in self.actions:
            button.configure(state='disabled')
        future = self.executor.submit(work)
        future.add_done_callback(lambda result: self.messages.put((result, done, on_error)))

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
                       'correction_limit_exceeded': 'Automatic correction blocked: offset exceeds the limit',
                       'local_clock_changed': 'Automatic correction blocked: local clock changed after measurement',
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
        if self.needs_setup and action != 'stop':
            self.settings(first_run=True)
            return
        if not self.controls_service:
            messagebox.showinfo('Service controls', 'Open the installed service configuration to control its service.', parent=self.root)
            return
        # Restart invokes the service's normal first cycle: no competing writer.
        if action == 'restart' and not messagebox.askokcancel('Check now', 'Restart the background service to perform a new check immediately?', parent=self.root):
            return
        self.submit(lambda: control_service(action), lambda _: self.banner.set('Service command completed. Refreshing status…'), self.service_error)

    def settings(self, first_run=False):
        if self.settings_dialog and self.settings_dialog.winfo_exists():
            self.settings_dialog.lift()
            return
        first_run = first_run or self.needs_setup
        problem = ''
        raw = dict(DEFAULTS, primary_server='', log_directory='./logs', check_interval_minutes=5)
        try:
            existing = json.loads(self.path.read_text(encoding='utf-8-sig'))
            if not isinstance(existing, dict):
                raise ValueError('Settings must be an object')
            if 'check_interval_seconds' in existing:
                raw.pop('check_interval_minutes', None)
            raw.update({key: value for key, value in existing.items() if key in KEYS})
            try:
                load_config(self.path)
            except ValueError as error:
                problem = str(error)
        except (OSError, ValueError) as error:
            problem = str(error)
        if first_run and platform.system() == 'Linux' and self.controls_service:
            raw['log_directory'] = raw.get('log_directory') if raw.get('log_directory') != './logs' else '/var/log/ntp-monitor'
        dialog = tk.Toplevel(self.root)
        self.settings_dialog = dialog
        dialog.title('Welcome to Network Time' if first_run else 'Network Time settings')
        ttk.Label(dialog, text='Choose your time servers, then Save and start.' if first_run else 'Edit settings and choose Save and start to apply them.', padding=12).pack(anchor='w')
        if problem:
            ttk.Label(dialog, text='Please review these settings: ' + problem + '\nYour original settings will be backed up when you save.', wraplength=650, padding=12).pack(anchor='w')
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill='both', expand=True)
        fields = [('primary_server', 'Primary NTP server'), ('secondary_server', 'Fallback NTP server'),
                  ('check_interval_minutes', 'Interval (1–15 minutes)'), ('timeout_seconds', 'Timeout (seconds)'),
                  ('resync_threshold_seconds', 'Correction threshold (seconds; blank = none)'),
                  ('max_clock_correction_seconds', 'Maximum automatic correction (seconds)'),
                  ('log_directory', 'XML / log directory'), ('log_rotation', 'Rotation (none / daily)'),
                  ('max_log_entries_per_file', 'History entry limit (blank = unlimited)'),
                  ('workstation_name', 'Host override (blank = automatic)')]
        variables = {}
        for row, (key, label) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=row, column=0, sticky='w', pady=5)
            value = raw.get(key, self.config.get(key) if self.config else '')
            if key == 'check_interval_minutes':
                try:
                    value = raw[key] if key in raw else float(raw.get('check_interval_seconds', 300)) / 60
                except (ValueError, TypeError):
                    value = 5
            variables[key] = tk.StringVar(value='' if value is None else str(value))
            if key == 'log_rotation':
                entry = ttk.Combobox(body, textvariable=variables[key], values=('none', 'daily'), state='readonly', width=35)
            else:
                entry = ttk.Entry(body, textvariable=variables[key], width=38)
            entry.grid(row=row, column=1, sticky='ew', padx=(15, 0))
            if key == 'log_directory':
                ttk.Button(body, text='Browse…', command=lambda: self.choose_directory(dialog, variables['log_directory'])).grid(row=row, column=2, padx=6)
        sync = tk.BooleanVar(value=raw.get('sync_system_clock') is True)
        ttk.Checkbutton(body, text='Adjust system clock (requires service privileges)', variable=sync).grid(row=len(fields), columnspan=2, sticky='w', pady=8)
        ttk.Label(body, text='Clock adjustment is optional. Corrections above the maximum are blocked and logged.').grid(row=len(fields) + 1, columnspan=2, sticky='w')

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
                    elif key in ('timeout_seconds', 'resync_threshold_seconds', 'max_clock_correction_seconds'):
                        value = float(value) if value else None
                    elif key in ('secondary_server', 'workstation_name') and not value:
                        value = None
                    values[key] = value
                values['sync_system_clock'] = sync.get()
                values['setup_complete'] = True
                save_config(self.path, values)
            except (OSError, ValueError, OverflowError) as error:
                messagebox.showerror('Settings not saved', str(error), parent=dialog)
                return
            dialog.destroy()
            self.needs_setup = False
            self.config = load_config(self.path)
            if self.controls_service:
                self.banner.set('Settings saved. Starting the background service…')
                self.submit(start_configured_service, self.started, self.service_error)
            else:
                self.banner.set('Settings saved. This configuration is not attached to an installed service.')
        ttk.Button(body, text='Save and start' if self.controls_service else 'Save settings', command=save).grid(row=len(fields) + 2, column=1, sticky='e', pady=(12, 0))
        ttk.Button(body, text='Cancel', command=dialog.destroy).grid(row=len(fields) + 2, column=0, sticky='w', pady=(12, 0))

    def started(self, state):
        self.service = state
        self.summary['service'].set('Running')
        self.banner.set('Monitoring has started. You can close this window; the service will continue.')
        self.poll_count = 0

    def service_error(self, error):
        messagebox.showerror('Service needs attention',
            'Your settings are saved, but the service action failed.\n\n' + str(error) +
            '\n\nOpen XML & diagnostics → View diagnostic details. If the service is missing, rerun the installer.', parent=self.root)

    def choose_directory(self, dialog, variable):
        selected = filedialog.askdirectory(parent=dialog, title='Choose XML and log folder')
        if selected:
            variable.set(selected)

    def show_diagnostics(self):
        if self.busy:
            self.banner.set('A status check is in progress. Please try diagnostic details again shortly.')
            return
        window = tk.Toplevel(self.root)
        window.title('Diagnostic details')
        window.geometry('800x480')
        text = tk.Text(window, wrap='word')
        text.pack(fill='both', expand=True, padx=12, pady=12)
        text.insert('1.0', 'Loading diagnostics…')
        def show(contents):
            if window.winfo_exists():
                text.delete('1.0', 'end')
                text.insert('1.0', contents)
        def copy():
            window.clipboard_clear()
            window.clipboard_append(text.get('1.0', 'end'))
        ttk.Button(window, text='Copy details', command=copy).pack(pady=8)
        self.submit(lambda: diagnostics(self.path), show, lambda error: show(str(error)))

    def about(self):
        messagebox.showinfo('About Network Time', 'NTP Client Monitor\nWindows and Linux background service\nPrimary/fallback NTP, clock correction, XML audit and configurable retention.\n\nClosing this window leaves the service running.\nNTS and time-server hosting are not implemented.', parent=self.root)

    def tick(self):
        self.summary['time'].set(datetime.now().astimezone().strftime('%d %b %Y  %H:%M:%S %Z'))
        try:
            future, done, on_error = self.messages.get_nowait()
            self.busy = False
            for index, button in enumerate(self.actions):
                button.configure(state='normal' if index >= 3 or self.controls_service else 'disabled')
            try:
                done(future.result())
            except Exception as error:
                self.banner.set(str(error))
                if on_error:
                    on_error(error)
        except queue.Empty:
            pass
        self.poll_count += 1
        if not self.busy and not self.needs_setup and not (self.settings_dialog and self.settings_dialog.winfo_exists()) and self.poll_count >= 15:
            self.poll_count = 0
            self.refresh()
        self.timer = self.root.after(200, self.tick)

    def close(self):
        for timer in (self.timer, self.setup_timer):
            if timer:
                self.root.after_cancel(timer)
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
