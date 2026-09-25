"""Build on the target OS/architecture; no cross-compilation."""
import os
import platform
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def build(name, source, extra=()):
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    '--onedir', '--name', name, '--paths', str(ROOT),
                    '--distpath', str(ROOT / 'dist'), '--workpath', str(ROOT / 'build' / name),
                    '--specpath', str(ROOT / 'build'), *extra, str(ROOT / source)],
                   cwd=str(ROOT), check=True)


if __name__ == '__main__':
    if sys.platform not in ('win32', 'linux'):
        sys.exit('Build on Windows or Linux; PyInstaller cannot cross-compile these installers.')
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        sys.exit('These installers target x64. Run the builder on an x64 OS/Python.')
    os.makedirs(ROOT / 'build', exist_ok=True)
    build('ntp-monitor', 'main.py')
    build('ntp-monitor-gui', 'gui.py', ('--windowed', '--uac-admin') if sys.platform == 'win32' else ())
    if sys.platform == 'win32':
        build('ntp-monitor-service', 'install/windows_service.py',
              ('--hidden-import', 'win32timezone'))
