#!/usr/bin/python3 -I
# SPDX-License-Identifier: GPL-3.0-only
"""Installed as pigrab. Convenience only; never changes networking or checks."""
import os
import sys


def command(user, args):
    return ['/usr/bin/sudo', '--', '/opt/pi-grab/venv/bin/python', '-I',
            '/opt/pi-grab/netguard.py', 'run', '--user', user, '--'] + list(args)


def main(args=None):
    args = sys.argv[1:] if args is None else list(args)
    if args in (['--help'], ['-h']):
        print('pigrab                     Interaktive Warteschlange\n'
              'pigrab URL [NAME]          Einzeldownload\n'
              'Einmalige Installation/VPN-Einrichtung: /opt/pi-grab/README.md\n'
              'Start nur im geprueften Tunnel; fehlende Einrichtung stoppt den Start.\n'
              'Erweiterte sichtbare Ausnahmen: --force, --skip-check; siehe README.')
        return 0
    try:
        if sys.platform != 'linux':
            raise ValueError('Start nur unter Linux.')
        if os.getuid() == 0 or os.getuid() != os.geteuid():
            raise ValueError('Als normalen Benutzer pigrab starten; sudo wird bei Bedarf selbst aufgerufen.')
        import pwd
        user = pwd.getpwuid(os.getuid()).pw_name
        argv = command(user, args)
        os.execv(argv[0], argv)
    except (OSError, ValueError, KeyError) as exc:
        print('FEHLER: ID=START_FAILED; EXIT_CODE=1; MESSAGE=' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
