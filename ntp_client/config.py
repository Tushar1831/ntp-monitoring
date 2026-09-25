"""Shared, side-effect-free configuration loading for CLI and service startup."""
import ipaddress
import json
import math
import os
import re


DEFAULTS = {
    'secondary_server': None, 'timeout_seconds': 5, 'log_rotation': 'none',
    'max_log_entries_per_file': 20000, 'sync_system_clock': False,
    'resync_threshold_seconds': 0.5, 'workstation_name': None,
}
KEYS = set(DEFAULTS) | {'primary_server', 'log_directory',
                        'check_interval_minutes', 'check_interval_seconds'}


def _number(key, value, minimum, maximum=None, integer=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (integer and not isinstance(value, int))):
        raise ValueError(f"{key}: expected {'integer' if integer else 'number'}")
    try:
        valid = math.isfinite(value) and value >= minimum
    except OverflowError:
        valid = False
    if not valid or (maximum is not None and value > maximum):
        raise ValueError(f'{key}: must be finite and between {minimum} and {maximum or "unbounded"}')
    return value


def _server(key, value):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{key}: expected a hostname or IPv4 address')
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        labels = value.rstrip('.').split('.')
        if (len(value) > 253 or all(c in '0123456789.' for c in value)
                or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                       for label in labels)):
            raise ValueError(f'{key}: invalid hostname or IPv4 address')
    else:
        if address.version != 4:
            raise ValueError(f'{key}: IPv6 is not supported by the current NTP transport')
    return value


def load_config(path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'{key}: duplicate configuration key')
            result[key] = value
        return result

    with open(path, encoding='utf-8') as stream:
        raw = json.load(stream, object_pairs_hook=unique_object)
    if not isinstance(raw, dict):
        raise ValueError('Configuration must be a JSON object')
    unknown = set(raw) - KEYS
    if unknown:
        raise ValueError('Unknown configuration keys: ' + ', '.join(sorted(unknown)))
    config = dict(DEFAULTS, **raw)
    config['primary_server'] = _server('primary_server', config.get('primary_server'))
    if config['secondary_server'] is not None:
        config['secondary_server'] = _server('secondary_server', config['secondary_server'])
    if 'check_interval_minutes' in raw and 'check_interval_seconds' in raw:
        raise ValueError('Specify only one of check_interval_minutes and check_interval_seconds')
    if 'check_interval_seconds' in raw:
        seconds = _number('check_interval_seconds', raw['check_interval_seconds'], 60, 900, integer=True)
    else:
        minutes = _number('check_interval_minutes', raw.get('check_interval_minutes', 5), 1, 15, integer=True)
        seconds = minutes * 60
    config.pop('check_interval_minutes', None)
    config['check_interval_seconds'] = seconds
    timeout = _number('timeout_seconds', config['timeout_seconds'], 0)
    if timeout == 0 or timeout > seconds:
        raise ValueError('timeout_seconds: must be positive and no greater than the check interval')
    if type(config['sync_system_clock']) is not bool:
        raise ValueError('sync_system_clock: expected true or false')
    if config['resync_threshold_seconds'] is not None:
        _number('resync_threshold_seconds', config['resync_threshold_seconds'], 0)
    if config['max_log_entries_per_file'] is not None:
        _number('max_log_entries_per_file', config['max_log_entries_per_file'], 1, integer=True)
    if config['log_rotation'] not in ('none', 'daily'):
        raise ValueError('log_rotation: expected none or daily')
    name = config['workstation_name']
    if name is not None and (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,199}', name)):
        raise ValueError('workstation_name: expected a safe filename component (letters, digits, dot, underscore, hyphen)')
    directory = config.get('log_directory')
    if not isinstance(directory, str) or not directory.strip() or any(ord(c) < 32 for c in directory):
        raise ValueError('log_directory: expected a nonempty path without control characters')
    if not os.path.isabs(directory):
        directory = os.path.join(os.path.dirname(os.path.abspath(path)), directory)
    config['log_directory'] = os.path.normpath(directory)
    return config
