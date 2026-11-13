#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only Pi inventory, no public connections, no private key output."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def command(argv):
    print('\n$ ' + ' '.join(argv))
    try:
        r = subprocess.run(argv, text=True, capture_output=True, timeout=10)
        print(r.stdout[:20000], end='')
        if r.returncode:
            print(f'EXIT_CODE={r.returncode} ({r.stderr[:300].strip()})')
    except (OSError, subprocess.SubprocessError) as e:
        print('UNGETESTET: ' + type(e).__name__)


def main():
    if sys.platform != 'linux':
        print('Pi-Inventur nur unter Linux ausfuehren.', file=sys.stderr)
        return 1
    print('Nur lokale Inventur; keine Status-/Videoanbieter werden kontaktiert.')
    print('Kernel/Architektur:', platform.platform(), platform.machine(), 'Python:', sys.version)
    for name in ('/proc/device-tree/model', '/etc/os-release', '/proc/meminfo', '/etc/resolv.conf', '/etc/nsswitch.conf'):
        print('\nFILE:', name)
        try:
            print(Path(name).read_text().replace('\x00', '')[:8000])
        except OSError as e:
            print(type(e).__name__)
    for args in ([['getconf', 'LONG_BIT'], ['df', '-hT', str(Path.home())], ['findmnt', '-T', str(Path.home())],
                  ['ip', '-j', '-d', 'link'], ['ip', '-j', 'address'], ['ip', '-j', 'route', 'show', 'table', 'all'],
                  ['ip', '-j', '-6', 'route', 'show', 'table', 'all'], ['ip', '-j', 'rule'], ['ip', '-j', '-6', 'rule'],
                  ['resolvectl', 'status'], ['nmcli', '-t', '-f', 'NAME,TYPE,DEVICE', 'connection', 'show', '--active'],
                  ['systemctl', 'is-active', 'ssh'], ['ss', '-lnt'], ['wg', 'show', 'interfaces'],
                  ['ffmpeg', '-version'], ['ffprobe', '-version'], ['curl', '--version'], ['dig', '-v'],
                  ['nft', '--version'], ['protonvpn', '--version'], ['protonvpn-cli', '--version']]):
        if shutil.which(args[0]):
            command(args)
        else:
            print('\nFEHLT:', args[0])
    print('\nProxyvariablen (nur Namen, keine Werte):', json.dumps([k for k in os.environ if 'proxy' in k.lower()]))
    print('Noch administrativ lokal zu pruefen: nft-Regeln, Proton-Kill-Switch/Split-Tunneling, VPN-Profil, Zielmedium, SSH-Fingerprint. Keine privaten Schluessel protokollieren.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
