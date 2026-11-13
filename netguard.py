#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Administrator-only namespace lifecycle. Never changes host routes/firewall.

Read README.md before setup. Private keys are never printed or passed in argv.
"""
import argparse
import base64
import configparser
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

if os.name == 'posix':
    import pwd

NS = 'grabvpn'
HOST_IF = 'grabwg0'
APP = Path('/opt/pi-grab')
IP = '/usr/sbin/ip'
WG = '/usr/bin/wg'
NFT = '/usr/sbin/nft'
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'}
STATE = Path('/var/lib/pi-grab-netguard')
RULES = '''table inet pigrab {
 chain input { type filter hook input priority 0; policy drop;
  iifname "lo" accept
  iifname "wg0" accept
 }
 chain output { type filter hook output priority 0; policy drop;
  oifname "lo" accept
  meta nfproto ipv4 oifname "wg0" accept
 }
 chain forward { type filter hook forward priority 0; policy drop; }
}
'''


def call(args, *, input_text=None, check=True):
    result = subprocess.run(args, input=input_text, text=True, capture_output=True, env=ENV, timeout=20)
    if check and result.returncode:
        # Some native errors echo configuration content: do not print it.
        raise ValueError(f'{Path(args[0]).name}: Exit {result.returncode}; Einrichtung angehalten.')
    return result


def inside(args, **kwargs):
    return call([IP, 'netns', 'exec', NS] + list(args), **kwargs)


def exists():
    return any(line.split()[0] == NS for line in call([IP, 'netns', 'list']).stdout.splitlines() if line.split())


def trusted_file(path, secret=False):
    if path.is_symlink() or path.resolve() != path:
        raise ValueError('Verknuepfungen in administrativen Pfaden nicht erlaubt.')
    s = path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & (0o077 if secret else 0o022):
        raise ValueError('Administrative Datei muss root gehoeren; Schluessel nur root lesbar, Code nicht fremd beschreibbar.')


def parse_profile(path):
    trusted_file(path, secret=True)
    text = path.read_text()
    if len(text) > 65536:
        raise ValueError('WireGuard-Profil zu gross.')
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    parser.optionxform = str
    parser.read_string(text)
    if set(parser.sections()) != {'Interface', 'Peer'}:
        raise ValueError('Genau ein Interface und ein Peer erforderlich.')
    interface, peer = parser['Interface'], parser['Peer']
    if set(interface) - {'PrivateKey', 'Address', 'DNS', 'MTU'} or set(peer) - {'PublicKey', 'PresharedKey', 'AllowedIPs', 'Endpoint', 'PersistentKeepalive'}:
        raise ValueError('Unbekannte Profiloption (insbesondere Hooks/Table/SaveConfig nicht zugelassen).')
    for section, key in ((interface, 'PrivateKey'), (peer, 'PublicKey')):
        if len(base64.b64decode(section[key], validate=True)) != 32:
            raise ValueError('Ungueltiger WireGuard-Schluessel.')
    if peer.get('PresharedKey') and len(base64.b64decode(peer['PresharedKey'], validate=True)) != 32:
        raise ValueError('Ungueltiger PresharedKey.')
    addresses = [ipaddress.ip_interface(s.strip()) for s in interface['Address'].split(',')]
    addresses4 = [str(a) for a in addresses if a.version == 4]
    if len(addresses4) != 1:
        raise ValueError('Genau eine IPv4-Tunneladresse erforderlich.')
    dns = [ipaddress.ip_address(s.strip()) for s in interface['DNS'].split(',')]
    dns4 = [str(a) for a in dns if a.version == 4 and not a.is_loopback and not a.is_unspecified]
    if not dns4 or len(dns4) > 3:
        raise ValueError('Ein bis drei numerische IPv4-VPN-DNS-Server erforderlich, kein Host-Stub.')
    endpoint, port = peer['Endpoint'].rsplit(':', 1)
    endpoint_ip = ipaddress.ip_address(endpoint.strip('[]'))
    if not endpoint_ip.is_global or not 1 <= int(port) <= 65535:
        raise ValueError('Numerischer oeffentlicher VPN-Endpoint mit Port erforderlich; keine Host-DNS-Aufloesung durch Setup.')
    allowed = {str(ipaddress.ip_network(s.strip())) for s in peer['AllowedIPs'].split(',')}
    if '0.0.0.0/0' not in allowed or allowed - {'0.0.0.0/0', '::/0'}:
        raise ValueError('Volltunnel AllowedIPs 0.0.0.0/0 erforderlich; optional ::/0 wird wegen IPv6-Sperre ignoriert.')
    mtu = int(interface.get('MTU', 1380))
    if not 1280 <= mtu <= 1420:
        raise ValueError('MTU muss zwischen 1280 und 1420 liegen.')
    keepalive = int(peer.get('PersistentKeepalive', '25'))
    if not 0 <= keepalive <= 65535:
        raise ValueError('Ungueltiger Keepalive.')
    clean = '[Interface]\nPrivateKey = ' + interface['PrivateKey'] + '\n\n[Peer]\nPublicKey = ' + peer['PublicKey'] + '\n'
    if peer.get('PresharedKey'):
        clean += 'PresharedKey = ' + peer['PresharedKey'] + '\n'
    clean += f'AllowedIPs = 0.0.0.0/0\nEndpoint = {peer["Endpoint"]}\nPersistentKeepalive = {keepalive}\n'
    return clean, addresses4[0], dns4, mtu


def setup(profile):
    if exists() or call([IP, 'link', 'show', HOST_IF], check=False).returncode == 0:
        raise ValueError('grabvpn/grabwg0 existiert bereits. Kein Ueberschreiben; Status pruefen und explizit entfernen.')
    clean, address, dns, mtu = parse_profile(profile)
    dnsdir = Path('/etc/netns') / NS
    if dnsdir.exists() or dnsdir.is_symlink() or STATE.exists() or STATE.is_symlink():
        raise ValueError('Namespace-DNS oder Verwaltungszustand existiert; kein fremder Zustand wird ersetzt.')
    created_ns = created_if = created_dns = created_state = False
    try:
        call([IP, 'netns', 'add', NS])
        created_ns = True
        # WireGuard's UDP socket stays in the host; plaintext sees no host NIC.
        call([IP, 'link', 'add', HOST_IF, 'type', 'wireguard'])
        created_if = True
        call([IP, 'link', 'set', HOST_IF, 'netns', NS])
        inside([IP, 'link', 'set', HOST_IF, 'name', 'wg0'])
        inside(['/usr/sbin/sysctl', '-q', '-w', 'net.ipv6.conf.all.disable_ipv6=1',
                'net.ipv6.conf.default.disable_ipv6=1', 'net.ipv6.conf.lo.disable_ipv6=1', 'net.ipv6.conf.wg0.disable_ipv6=1'])
        inside([NFT, '-f', '-'], input_text=RULES)
        # /run private temp file, not the SD-card home or command line.
        fd, name = tempfile.mkstemp(prefix='pigrab-wg-', dir='/run')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(clean)
            inside([WG, 'setconf', 'wg0', name])
        finally:
            Path(name).unlink(missing_ok=True)
        inside([IP, 'address', 'add', address, 'dev', 'wg0'])
        inside([IP, 'link', 'set', 'lo', 'up'])
        inside([IP, 'link', 'set', 'wg0', 'mtu', str(mtu), 'up'])
        inside([IP, 'route', 'add', 'default', 'dev', 'wg0'])
        dnsdir.mkdir(parents=True, mode=0o755)
        created_dns = True
        (dnsdir / 'resolv.conf').write_text(''.join(f'nameserver {a}\n' for a in dns) + 'options timeout:3 attempts:1\n')
        # Avoid local nscd/systemd-resolved NSS sockets bypassing nameserver selection.
        (dnsdir / 'nsswitch.conf').write_text('passwd: files\ngroup: files\nshadow: files\nhosts: files dns\nnetworks: files\n')
        (dnsdir / 'resolv.conf').chmod(0o644)
        (dnsdir / 'nsswitch.conf').chmod(0o644)
        STATE.mkdir(mode=0o755)
        STATE.chmod(0o755)
        created_state = True
        (STATE / 'namespace.id').write_text(str(Path('/run/netns/' + NS).stat().st_ino) + '\n')
        (STATE / 'namespace.id').chmod(0o644)
        check_rules()
        print('grabvpn eingerichtet: nur lo/wg0, IPv6 gesperrt, eigene VPN-DNS-Server. Host-Routen/Firewall unveraendert.')
    except BaseException:
        if created_ns:
            call([IP, 'netns', 'del', NS], check=False)
        if created_if:
            call([IP, 'link', 'del', HOST_IF], check=False)
        if created_dns:
            shutil.rmtree(dnsdir)
        if created_state:
            shutil.rmtree(STATE)
        raise


def check_rules():
    if not exists():
        raise ValueError('Download-Namespace fehlt; zuerst setup ausfuehren.')
    # Compare the full semantic nftables JSON with the fixed reference below.
    # A changed nft JSON representation fails closed and needs target validation.
    rules = json.loads(inside([NFT, '-j', 'list', 'ruleset']).stdout)
    meaningful = []
    for item in rules.get('nftables', []):
        if 'metainfo' in item:
            continue
        normalized = json.loads(json.dumps(item))
        for block in normalized.values():
            for key in ('handle', 'index'):
                block.pop(key, None)
        meaningful.append(normalized)
    # Fixed expected objects; inet rules deliberately cover IPv4+IPv6.
    expected = [
        {'table': {'family': 'inet', 'name': 'pigrab'}},
        {'chain': {'family': 'inet', 'table': 'pigrab', 'name': 'input', 'type': 'filter', 'hook': 'input', 'prio': 0, 'policy': 'drop'}},
        {'rule': {'family': 'inet', 'table': 'pigrab', 'chain': 'input', 'expr': [{'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'lo'}}, {'accept': None}]}},
        {'rule': {'family': 'inet', 'table': 'pigrab', 'chain': 'input', 'expr': [{'match': {'op': '==', 'left': {'meta': {'key': 'iifname'}}, 'right': 'wg0'}}, {'accept': None}]}},
        {'chain': {'family': 'inet', 'table': 'pigrab', 'name': 'output', 'type': 'filter', 'hook': 'output', 'prio': 0, 'policy': 'drop'}},
        {'rule': {'family': 'inet', 'table': 'pigrab', 'chain': 'output', 'expr': [{'match': {'op': '==', 'left': {'meta': {'key': 'oifname'}}, 'right': 'lo'}}, {'accept': None}]}},
        {'rule': {'family': 'inet', 'table': 'pigrab', 'chain': 'output', 'expr': [{'match': {'op': '==', 'left': {'meta': {'key': 'nfproto'}}, 'right': 'ipv4'}}, {'match': {'op': '==', 'left': {'meta': {'key': 'oifname'}}, 'right': 'wg0'}}, {'accept': None}]}},
        {'chain': {'family': 'inet', 'table': 'pigrab', 'name': 'forward', 'type': 'filter', 'hook': 'forward', 'prio': 0, 'policy': 'drop'}},
    ]
    if meaningful != expected:
        raise ValueError('Namespace-nftables weicht vom engen Soll ab; kein Start. Unterschied nur lokal untersuchen.')
    for filename in ('resolv.conf', 'nsswitch.conf'):
        trusted_file(Path('/etc/netns') / NS / filename)
    trusted_file(STATE / 'namespace.id')
    if int((STATE / 'namespace.id').read_text()) != Path('/run/netns/' + NS).stat().st_ino:
        raise ValueError('Namespace-Identitaet abweichend.')
    resolv = (Path('/etc/netns') / NS / 'resolv.conf').read_text()
    values = re.findall(r'^nameserver\s+(\S+)\s*$', resolv, flags=re.M)
    if not values or any(ipaddress.ip_address(s).version != 4 or ipaddress.ip_address(s).is_loopback for s in values):
        raise ValueError('Namespace-DNS fehlt oder verwendet einen Host-Stub.')


def account_and_installation(user):
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError('Downloadbenutzer darf nicht root sein.')
    if APP.resolve() != APP:
        raise ValueError('Installationspfad ist eine Verknuepfung.')
    for directory in (APP, APP / 'venv'):
        s = directory.stat()
        if s.st_uid != 0 or s.st_mode & 0o022:
            raise ValueError('Installation muss root gehoeren und darf nicht fremd beschreibbar sein.')
    trusted_file(APP / 'grab.py')
    trusted_file(APP / 'voe_resolver.py')
    trusted_file(APP / 'netguard.py')
    return account


def run(user, args):
    check_rules()
    account_and_installation(user)
    # A private mount namespace hides all host /run sockets, notably nscd,
    # systemd-resolved and D-Bus. Only then are privileges dropped.
    command = [IP, 'netns', 'exec', NS, '/usr/bin/unshare', '--mount', '--propagation', 'private',
               str(APP / 'venv/bin/python'), '-I', str(APP / 'netguard.py'), 'exec-user', '--user', user, '--'] + args
    os.execve(IP, command, ENV)


def exec_user(user, args):
    account = account_and_installation(user)
    marker = STATE / 'namespace.id'
    trusted_file(marker)
    if int(marker.read_text()) != Path('/proc/self/ns/net').stat().st_ino:
        raise ValueError('Interner Start nur im eingerichteten Download-Namespace.')
    # A systemd-resolved /etc/resolv.conf symlink may point into /run. Save
    # the already namespace-bound content and reconstruct ONLY that target.
    local_files = []
    for name in ('resolv.conf', 'nsswitch.conf'):
        path = Path('/etc') / name
        target = path.resolve(strict=True)
        if target.is_relative_to('/run'):
            local_files.append((target, path.read_bytes()))
    call(['/usr/bin/mount', '-t', 'tmpfs', '-o', 'mode=0755,nosuid,nodev,noexec,size=4M', 'tmpfs', '/run'])
    old_mask = os.umask(0o022)
    try:
        for path, content in local_files:
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o644)
    finally:
        os.umask(old_mask)
    # setpriv drops supplementary groups and all capabilities; no sudoers entry.
    command = ['/usr/bin/setpriv', '--reuid', str(account.pw_uid),
               '--regid', str(account.pw_gid), '--clear-groups', '--bounding-set=-all',
               '--inh-caps=-all', '--ambient-caps=-all', '--no-new-privs',
               '/usr/bin/env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'LANG=C.UTF-8',
               'HOME=' + account.pw_dir, 'USER=' + user, 'LOGNAME=' + user,
               'PYTHONNOUSERSITE=1', 'PYTHONDONTWRITEBYTECODE=1',
               str(APP / 'venv/bin/python'), '-I', str(APP / 'grab.py')] + args
    # Do not inherit caller directory/mounts, proxy variables or stdin network sockets.
    os.chdir(account.pw_dir)
    os.execve(command[0], command, ENV)


def down():
    if not exists():
        raise ValueError('Namespace fehlt; nichts geloescht.')
    pids = call([IP, 'netns', 'pids', NS]).stdout.strip()
    if pids:
        raise ValueError('Namespace hat aktive Prozesse; kein Loeschen und kein Beenden fremder Downloads.')
    check_rules()
    call([IP, 'netns', 'del', NS])
    directory = Path('/etc/netns') / NS
    if directory.resolve() != directory or set(p.name for p in directory.iterdir()) != {'resolv.conf', 'nsswitch.conf'}:
        raise ValueError('DNS-Verzeichnis abweichend; manuell pruefen, nicht rekursiv geloescht.')
    for name in ('resolv.conf', 'nsswitch.conf'):
        (directory / name).unlink()
    directory.rmdir()
    if STATE.resolve() != STATE or set(p.name for p in STATE.iterdir()) != {'namespace.id'}:
        raise ValueError('Verwaltungszustand abweichend; manuell pruefen.')
    (STATE / 'namespace.id').unlink()
    STATE.rmdir()
    print('Nur grabvpn und dessen DNS-Dateien entfernt. Paralleles Proton/SSH nicht umkonfiguriert.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    setup_parser = sub.add_parser('setup')
    setup_parser.add_argument('--profile', type=Path, required=True)
    sub.add_parser('status')
    sub.add_parser('down')
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--user', required=True)
    run_parser.add_argument('args', nargs=argparse.REMAINDER)
    internal = sub.add_parser('exec-user', help=argparse.SUPPRESS)
    internal.add_argument('--user', required=True)
    internal.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        if sys.platform != 'linux' or os.geteuid() != 0:
            raise ValueError('Nur auf Linux mit Administratorrechten ausfuehren.')
        os.umask(0o077)
        if args.action == 'setup':
            setup(args.profile.absolute())
        elif args.action == 'run':
            run(args.user, args.args[1:] if args.args[:1] == ['--'] else args.args)
        elif args.action == 'exec-user':
            exec_user(args.user, args.args[1:] if args.args[:1] == ['--'] else args.args)
        elif args.action == 'down':
            down()
        else:
            check_rules()
            print(inside([IP, '-j', '-d', 'link', 'show']).stdout)
            print(inside([IP, '-j', 'route', 'show', 'table', 'all']).stdout)
            print('Firewall/DNS-Soll geprueft. Kein Nachweis eines erfolgreichen VPN-Handshakes oder Downloads.')
        return 0
    except (OSError, ValueError, KeyError, configparser.Error, subprocess.SubprocessError) as exc:
        message = str(exc) if type(exc) is ValueError else 'Profilsyntax, Rechte, Programme oder Betriebssystem ungueltig.'
        print('FEHLER: ID=NET_GUARD_ADMIN_FAILED; EXIT_CODE=2; MESSAGE=' + message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
