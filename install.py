#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Install source only; no package/network/VPN/firewall changes."""
import os
from pathlib import Path
import shutil
import sys


def main():
    if sys.platform != 'linux' or os.geteuid() != 0:
        print('Nur auf Linux mit sudo ausfuehren.', file=sys.stderr)
        return 1
    if sys.version_info < (3, 11, 5):
        print('Python ab 3.11.5 erforderlich; keine automatische System-Python-Aktualisierung.', file=sys.stderr)
        return 1
    target = Path('/opt/pi-grab')
    command = Path('/usr/local/bin/pigrab')
    source = Path(__file__).resolve().parent
    if target.exists() or target.is_symlink() or command.exists() or command.is_symlink():
        print('/opt/pi-grab oder /usr/local/bin/pigrab existiert; kein automatisches Ueberschreiben.', file=sys.stderr)
        return 1
    os.umask(0o022)
    # Explicit file set: no Windows binaries, caches, test results or credentials.
    target.mkdir(mode=0o755)
    command_created = False
    try:
        names = ['grab.py', 'start.py', 'netguard.py', 'voe_resolver.py', 'inventory.py', 'config.toml', 'requirements.txt', 'requirements.lock',
                 'LICENSE', 'README.md', 'SECURITY.md', 'SOURCES.md', 'VERBINDUNG.md', 'TESTBERICHT.md', 'OPTIMIERUNG.md', 'vendor-sha256.json', 'voe_dl', 'tests', 'wheels']
        for name in names:
            src, dst = source / name, target / name
            if src.is_symlink():
                raise ValueError('Verknuepfungen im Quellprojekt nicht erlaubt.')
            if src.is_dir():
                if any(p.is_symlink() for p in src.rglob('*')):
                    raise ValueError('Verknuepfung im Quellprojekt.')
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                shutil.copyfile(src, dst)
        for p in [target] + list(target.rglob('*')):
            os.chown(p, 0, 0)
            p.chmod(0o755 if p.is_dir() else 0o644)
        command.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        fd = os.open(command, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o755)
        command_created = True
        with os.fdopen(fd, 'wb') as stream:
            stream.write((target / 'start.py').read_bytes())
        os.chown(command, 0, 0)
        command.chmod(0o755)
        print('Quellen installiert. Abhaengigkeiten und VPN sind noch NICHT eingerichtet. Weiter mit README.md.')
        return 0
    except BaseException:
        if command_created:
            command.unlink(missing_ok=True)
        # New fixed directory only; never remove an existing installation.
        if target.resolve() == Path('/opt/pi-grab'):
            shutil.rmtree(target)
        raise


if __name__ == '__main__':
    sys.exit(main())
