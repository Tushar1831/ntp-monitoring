"""Package an existing Linux x64 PyInstaller bundle as DEB and RPM.

Run on a Linux packaging host with dpkg-deb and rpmbuild installed. Build the
bundle on glibc 2.34 (see workflow) for the declared Ubuntu 22.04+/EL9 baseline.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
POST = '''#!/bin/sh
set -e
mkdir -p /var/log/ntp-monitor
chmod 0750 /var/log/ntp-monitor
if [ -d /run/systemd/system ]; then
    systemctl daemon-reload
    if /opt/ntp-monitor/ntp-monitor --check-config --require-setup; then
        systemctl enable ntp-monitor.service
        systemctl restart ntp-monitor.service
    else
        systemctl disable ntp-monitor.service
        systemctl stop ntp-monitor.service
        echo 'Open NTP Client Monitor to finish setup.'
    fi
fi
'''
PRE = '''#!/bin/sh
set -e
if [ -d /run/systemd/system ]; then
    systemctl stop ntp-monitor.service
    if [ "$1" = remove ] || [ "$1" = 0 ]; then
        systemctl disable ntp-monitor.service
    fi
fi
'''
POST_REMOVE = '''#!/bin/sh
set -e
if [ -d /run/systemd/system ]; then systemctl daemon-reload; fi
'''


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    path.chmod(mode)


def stage(destination):
    bundle = ROOT / 'dist' / 'ntp-monitor'
    if not (bundle / 'ntp-monitor').is_file():
        raise RuntimeError('Build the Linux bundle first: python scripts/build_bundle.py')
    shutil.copytree(bundle, destination / 'opt' / 'ntp-monitor', symlinks=True)
    gui = ROOT / 'dist' / 'ntp-monitor-gui'
    if not (gui / 'ntp-monitor-gui').is_file():
        raise RuntimeError('Desktop bundle is missing; rebuild with scripts/build_bundle.py')
    shutil.copytree(gui, destination / 'opt/ntp-monitor/gui', symlinks=True)
    config = json.loads((ROOT / 'config.json').read_text())
    config['log_directory'] = '/var/log/ntp-monitor'
    config['setup_complete'] = False
    write(destination / 'etc/ntp-monitor/config.json', json.dumps(config, indent=2) + '\n', 0o640)
    (destination / 'etc/ntp-monitor').chmod(0o750)
    write(destination / 'usr/lib/systemd/system/ntp-monitor.service',
          (ROOT / 'packaging/linux/ntp-monitor.service').read_text())
    write(destination / 'usr/bin/ntp-monitor-gui',
          (ROOT / 'packaging/linux/ntp-monitor-gui').read_text(), 0o755)
    write(destination / 'usr/share/applications/ntp-monitor.desktop',
          (ROOT / 'packaging/linux/ntp-monitor.desktop').read_text())
    for source in (ROOT / 'schemas').glob('*.xsd'):
        write(destination / 'usr/share/ntp-monitor' / source.name, source.read_text())


def build(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Version must be MAJOR.MINOR.PATCH')
    executable = ROOT / 'dist/ntp-monitor/ntp-monitor'
    with executable.open('rb') as stream:
        header = stream.read(20)
    if header[:6] != b'\x7fELF\x02\x01' or header[18:20] != b'\x3e\x00':
        raise ValueError('Expected a Linux x86-64 ELF bundle; rebuild on the target platform')
    for tool in ('dpkg-deb', 'rpmbuild', 'file', 'strip'):
        if not shutil.which(tool):
            raise RuntimeError(f'Install build tool: {tool}')
    output = ROOT / 'artifacts'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ntp-package-') as temporary:
        work = Path(temporary)
        payload = work / 'payload'
        stage(payload)
        deb = work / 'deb'
        shutil.copytree(payload, deb, symlinks=True)
        write(deb / 'DEBIAN/control', f'''Package: ntp-monitor
Version: {version}
Architecture: amd64
Maintainer: NTP Client Monitor maintainers
Section: admin
Priority: optional
Depends: libc6 (>= 2.34), systemd, zlib1g, policykit-1, libx11-6, libxft2, libxss1, libfontconfig1
Description: Standalone NTP monitor and clock synchronization service
 Bundles the Python runtime. No system Python or pip installation is needed.
''')
        write(deb / 'DEBIAN/conffiles', '/etc/ntp-monitor/config.json\n')
        for name, script in [('postinst', POST), ('prerm', PRE), ('postrm', POST_REMOVE)]:
            write(deb / 'DEBIAN' / name, script, 0o755)
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(deb),
                        str(output / f'ntp-monitor_{version}_amd64.deb')], check=True)
        top = work / 'rpm'
        for name in ('BUILD', 'BUILDROOT', 'RPMS', 'SOURCES', 'SPECS', 'SRPMS'):
            (top / name).mkdir(parents=True)
        spec = f'''Name: ntp-monitor
Version: {version}
Release: 1
Summary: Standalone NTP monitor and synchronization service
License: LicenseRef-Proprietary
BuildArch: x86_64
AutoReqProv: no
Requires: glibc >= 2.34, systemd, zlib, polkit, libX11, libXft, libXScrnSaver, fontconfig
%description
Bundles Python; no system Python or pip is needed.
%prep
%build
%install
mkdir -p %{{buildroot}}
cp -a {payload}/. %{{buildroot}}/
%preun
if [ "$1" = 0 ] && [ -d /run/systemd/system ]; then
    systemctl stop ntp-monitor.service
    systemctl disable ntp-monitor.service
fi
%posttrans
{POST.split(chr(10), 1)[1]}
%postun
{POST_REMOVE.split(chr(10), 1)[1]}
%files
%defattr(-,root,root,-)
/opt/ntp-monitor
%dir %attr(0750,root,root) /etc/ntp-monitor
%config(noreplace) %attr(0640,root,root) /etc/ntp-monitor/config.json
/usr/lib/systemd/system/ntp-monitor.service
/usr/share/ntp-monitor
/usr/bin/ntp-monitor-gui
/usr/share/applications/ntp-monitor.desktop
'''
        spec_path = top / 'SPECS/ntp-monitor.spec'
        write(spec_path, spec)
        subprocess.run(['rpmbuild', '--define', f'_topdir {top}', '--define',
                        '_build_id_links none', '-bb', str(spec_path)], check=True)
        for rpm in (top / 'RPMS').rglob('*.rpm'):
            shutil.copy2(rpm, output / rpm.name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', default='1.1.0')
    build(parser.parse_args().version)
