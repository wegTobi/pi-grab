#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""PiGrab: bounded processes, guarded networking and verified publication."""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import html
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import unicodedata
import urllib.parse
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voe_resolver import UA, valid_url

APP = Path(__file__).resolve().parent
YDL = str(APP / 'venv/bin/yt-dlp')
FFMPEG = '/usr/bin/ffmpeg'
FFPROBE = '/usr/bin/ffprobe'
IP = '/usr/sbin/ip'
CURL = '/usr/bin/curl'
DIG = '/usr/bin/dig'
NS = 'grabvpn'
ISO_COUNTRIES = set(('AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ '
                     'CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR '
                     'GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP '
                     'KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ '
                     'NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW '
                     'SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ '
                     'UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW').split())


class Failure(Exception):
    def __init__(self, code, ident, message):
        super().__init__(message)
        self.code, self.ident = code, ident


def fail(code, ident, message):
    raise Failure(code, ident, message)


def safe_text(text):
    """Do not persist signed URLs; strip terminal control characters too."""
    text = re.sub(r'https?://[^\s<>"\']+', '[URL entfernt]', str(text))
    return ''.join(c for c in text if c in '\n\r\t' or unicodedata.category(c)[0] != 'C')


def error(exc):
    print(f'FEHLER: ID={exc.ident}; EXIT_CODE={exc.code}; MESSAGE={safe_text(exc)}', file=sys.stderr)


def video_name(title):
    value = html.unescape(str(title)).strip()
    value = re.sub(r'^Watch\s+', '', value, flags=re.I)
    value = re.sub(r'\s*[-|]\s*VOE\s*$', '', value, flags=re.I)
    value = re.sub(r'(\.(mkv|mp4|avi|webm|mov))+$', '', value, flags=re.I)
    value = ''.join('-' if c in '<>:"/\\|?*' or unicodedata.category(c)[0] == 'C' else c for c in value)
    value = re.sub(r'\.{2,}', '.', value)
    value = re.sub(r'\s+', '_', value.strip().rstrip('. ')).strip('._')
    value = unicodedata.normalize('NFC', value)[:120]
    # Linux NAME_MAX counts bytes. Leave room for extension and collision suffix.
    while len(value.encode('utf-8')) > 220:
        value = value[:-1]
    if not value:
        fail(1, 'OUTPUT_NAME_INVALID', 'Kein verwendbarer Dateiname.')
    return value


def load_config(path):
    try:
        data = tomllib.loads(Path(path).read_text(encoding='utf-8-sig'))
        required = {'storage', 'home_country', 'home_country_names', 'blocked_orgs',
                    'allowed_patterns', 'probe_url', 'download_timeout_sec', 'voe_hosts'}
        if set(data) != required:
            raise ValueError('Fehlende oder unbekannte Konfigurationseintraege')
        for key in ('home_country_names', 'blocked_orgs', 'allowed_patterns', 'voe_hosts'):
            if not isinstance(data[key], list) or not data[key] or any(not isinstance(x, str) or not x.strip() for x in data[key]):
                raise ValueError(f'Ungueltige Liste: {key}')
        for pattern in data['blocked_orgs'] + data['allowed_patterns']:
            re.compile(pattern, re.I)
        timeout = data['download_timeout_sec']
        if type(timeout) is not int or not 1 <= timeout <= 2147483:
            raise ValueError('download_timeout_sec muss eine ganze Zahl von 1 bis 2147483 sein')
        if not re.fullmatch('[A-Z]{2}', data['home_country']):
            raise ValueError('home_country muss aus zwei Grossbuchstaben bestehen')
        if not isinstance(data['storage'], str) or not data['storage'].strip():
            raise ValueError('storage fehlt')
        valid_url(data['probe_url'])
        return data
    except (OSError, ValueError, TypeError, KeyError) as exc:
        fail(1, 'CONFIG_INVALID', str(exc))


@dataclasses.dataclass
class Result:
    code: int
    out: str
    err: str = ''
    timed_out: bool = False


class Runner:
    def __init__(self):
        self.position = (1, 1)

    def run(self, argv, *, timeout=120, live=False, cwd=None, input_text=None):
        # Allow-list environment: no proxies, Python injection, netrc or yt-dlp config.
        env = {k: v for k, v in os.environ.items() if k in ('HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'SYSTEMROOT', 'WINDIR')}
        env.update(PATH='/usr/sbin:/usr/bin:/sbin:/bin', YTDLP_NO_PLUGINS='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        if cwd:
            env.update(TMPDIR=str(cwd), TMP=str(cwd), TEMP=str(cwd), XDG_CACHE_HOME=str(cwd / 'cache'), XDG_CONFIG_HOME=str(cwd / 'config'))
        kwargs = {'start_new_session': True} if os.name == 'posix' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
        try:
            proc = subprocess.Popen(list(map(str, argv)), shell=False, cwd=cwd, env=env,
                                    stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        except OSError:
            fail(1, 'PROCESS_START_FAILED', f'Programm nicht startbar: {Path(argv[0]).name}')
        messages = queue.Queue(maxsize=256)
        def reader(stream, channel):
            try:
                for line in iter(lambda: stream.readline(65536), b''):
                    messages.put((channel, line.decode('utf-8', errors='replace')))
            finally:
                stream.close()
                messages.put((channel, None))
        for ch, stream in enumerate((proc.stdout, proc.stderr)):
            threading.Thread(target=reader, args=(stream, ch), daemon=True).start()
        if input_text is not None:
            proc.stdin.write(input_text.encode('utf-8'))
            proc.stdin.close()
        buffers = [[], []]
        sizes = [0, 0]
        started, heartbeat, ended, expired = time.monotonic(), 30, 0, False
        def kill_group():
            if os.name == 'posix':
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            elif proc.poll() is None:
                subprocess.run(['taskkill.exe', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
                if proc.poll() is None:
                    proc.kill()
        try:
            while ended < 2 or proc.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= timeout and not expired:
                    expired = True
                    kill_group()
                if live and elapsed >= heartbeat:
                    print(f'läuft noch, {self.position[0]} von {self.position[1]}', flush=True)
                    heartbeat += 30
                try:
                    channel, line = messages.get(timeout=0.05)
                except queue.Empty:
                    continue
                if line is None:
                    ended += 1
                    continue
                if live:
                    print(safe_text(line), end='', flush=True)
                else:
                    # Capture JSON/diagnostics only where the caller needs them.
                    # Live transfer output is shown once, never retained here.
                    buffers[channel].append(line)
                    sizes[channel] += len(line)
                    if sizes[channel] > 16 * 1024 * 1024:
                        kill_group()
                        fail(1, 'PROCESS_OUTPUT_TOO_LARGE', 'Prozessausgabe zu gross.')
            code = proc.wait()
            if code is None:
                fail(1, 'PROCESS_EXIT_MISSING', 'Prozess ohne Exit-Code.')
            return Result(code, ''.join(buffers[0]), ''.join(buffers[1]), expired)
        finally:
            # Also kill descendants left behind after the leader exited.
            kill_group()
            proc.wait()


def locked_file(path):
    """Portable test support; production is Linux and uses flock."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    file = os.fdopen(fd, 'r+b', buffering=0)
    try:
        if os.name == 'posix':
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            import msvcrt
            if os.fstat(fd).st_size == 0:
                file.write(b'0')
            file.seek(0)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return file
    except BaseException:
        file.close()
        raise


@contextlib.contextmanager
def gate(path):
    deadline = time.monotonic() + 15
    while True:
        try:
            lock = locked_file(path)
            break
        except (BlockingIOError, PermissionError):
            if time.monotonic() >= deadline:
                fail(1, 'STORAGE_BUSY', 'Arbeitsablage ist gesperrt.')
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.close()


def secure_directory(path):
    path = Path(os.path.abspath(Path(path).expanduser()))
    if path.resolve() != path:
        fail(1, 'STORAGE_SYMLINK', 'Ablage oder ein Elternpfad ist eine Verknuepfung.')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or (os.name == 'posix' and (s.st_uid != os.geteuid() or s.st_mode & 0o022)):
        fail(1, 'STORAGE_UNSAFE', 'Ablage muss dem Benutzer gehoeren und darf nicht fremd beschreibbar sein.')
    return path


def safe_tree(path):
    if path.is_symlink() or not path.is_dir():
        return False
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            mode = (Path(root) / name).lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                return False
    return True


class Store:
    def __init__(self, base):
        self.base = secure_directory(base)
        self.output = secure_directory(self.base / 'finished')
        self.work = secure_directory(self.base / '.work')
        self.state = secure_directory(self.base / '.state')
        if self.output.stat().st_dev != self.work.stat().st_dev:
            fail(1, 'STORAGE_FILESYSTEM', 'Arbeits- und Ausgabeordner muessen auf demselben Dateisystem liegen.')
        self.gatepath = self.base / '.work.lock'

    def cleanup(self):
        removed = 0
        with gate(self.gatepath):
            for path in self.work.iterdir():
                if not re.fullmatch('[a-f0-9]{32}', path.name) or path.is_symlink():
                    continue
                try:
                    if time.time() - path.stat().st_mtime <= 86400 or not safe_tree(path):
                        continue
                    lock = locked_file(path / '.active.lock')
                    try:
                        if os.name == 'posix':
                            shutil.rmtree(path)
                        else:
                            lock.close()
                            shutil.rmtree(path)
                        removed += 1
                    finally:
                        lock.close()
                except OSError:
                    print(f'WARNUNG: Alter Arbeitsordner bleibt (aktiv/gesperrt/unsicher): {path.name}')
        print(f'Arbeitsordner bereinigt: {removed} (älter als 24 Stunden).')
        return removed

    @contextlib.contextmanager
    def workspace(self):
        with gate(self.gatepath):
            path = self.work / uuid.uuid4().hex
            path.mkdir(mode=0o700)
            lock = locked_file(path / '.active.lock')
        try:
            yield path
        finally:
            with gate(self.gatepath):
                try:
                    if path.parent != self.work or not safe_tree(path):
                        raise OSError('Unsicherer Arbeitsordner')
                    if os.name != 'posix':
                        lock.close()
                    shutil.rmtree(path)
                except OSError:
                    print(f'WARNUNG: Arbeitsdaten nicht entfernt: {path.name}', file=sys.stderr)
                finally:
                    lock.close()

    def publish(self, source, name, extension):
        if source.is_symlink() or not source.is_file() or source.stat().st_nlink != 1:
            fail(1, 'PUBLISH_SOURCE_INVALID', 'Ungueltige Veroeffentlichungsquelle.')
        with source.open('r+b') as f:
            os.fsync(f.fileno())
        with gate(self.gatepath):
            for index in range(1, 10000):
                suffix = '' if index == 1 else f'_{index}'
                candidate = name[:120-len(suffix)] + suffix
                if any((self.output / (candidate + ext)).exists() for ext in ('.mp4', '.mkv', '.avi')):
                    continue
                target = self.output / (candidate + extension)
                try:
                    # Atomic no-replace, including across parallel instances.
                    if os.name == 'nt':
                        # Windows-only development tests; rename refuses existing
                        # targets there. Production main still rejects Windows.
                        os.rename(source, target)
                    else:
                        os.link(source, target, follow_symlinks=False)
                except FileExistsError:
                    continue
                except OSError:
                    fail(1, 'PUBLISH_FAILED', 'Atomare Veroeffentlichung fehlgeschlagen; POSIX-Dateisystem mit Hardlinks erforderlich.')
                if os.name != 'nt':
                    source.unlink()
                if os.name == 'posix':
                    fd = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
                return target
        fail(1, 'OUTPUT_COLLISION_LIMIT', 'Zu viele gleichnamige Dateien.')

    def last_ip(self, ip):
        try:
            with gate(self.gatepath):
                fd, temporary = tempfile.mkstemp(prefix='ip-', dir=self.state)
                try:
                    with os.fdopen(fd, 'w', encoding='ascii') as f:
                        f.write(ip + '\n')
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(temporary, self.state / '.last_exit_ip')
                finally:
                    Path(temporary).unlink(missing_ok=True)
        except OSError:
            print('WARNUNG: Fertige Datei vorhanden; letzte Exit-IP konnte nicht gespeichert werden.')


def ensure_guard(runner):
    """No environment flag is accepted as a substitute for the namespace."""
    if sys.platform != 'linux':
        fail(1, 'PLATFORM_UNSUPPORTED', 'Produktiver Start nur unter Linux; Windows-Tests sind keine Pi-Installation.')
    try:
        ns = Path('/var/lib/pi-grab-netguard/namespace.id')
        if ns.is_symlink() or ns.stat().st_uid != 0 or ns.stat().st_mode & 0o022 or int(ns.read_text()) != Path('/proc/self/ns/net').stat().st_ino:
            raise ValueError('Falscher Netzwerk-Namespace')
        mounts = [line.split() for line in Path('/proc/self/mountinfo').read_text().splitlines()]
        if not any(m[4] == '/run' and {'nosuid', 'nodev', 'noexec'} <= set(m[5].split(',')) and m[m.index('-')+1] == 'tmpfs' for m in mounts):
            raise ValueError('Host-Dienstsockets unter /run sind nicht isoliert')
        status = Path('/proc/self/status').read_text()
        if os.geteuid() == 0 or not re.search(r'^CapEff:\s*0+$', status, re.M) or not re.search(r'^NoNewPrivs:\s*1$', status, re.M):
            raise ValueError('Benutzerrechte/Capabilities unzulaessig')
        result = runner.run([IP, '-j', '-d', 'link', 'show'], timeout=5)
        links = json.loads(result.out) if result.code == 0 and not result.timed_out else []
        if {i['ifname'] for i in links} != {'lo', 'wg0'}:
            raise ValueError('Nur lo und wg0 zulaessig')
        wg = next(i for i in links if i['ifname'] == 'wg0')
        if wg.get('linkinfo', {}).get('info_kind') != 'wireguard':
            raise ValueError('wg0 ist kein WireGuard-Interface')
        # All present namespace interfaces, including virtual ones, are covered.
        for interface in ('all', 'default', 'lo', 'wg0'):
            if Path(f'/proc/sys/net/ipv6/conf/{interface}/disable_ipv6').read_text().strip() != '1':
                raise ValueError('IPv6 ist im Download-Namespace nicht vollstaendig deaktiviert')
    except (OSError, ValueError, KeyError, StopIteration, Failure):
        fail(2, 'NET_GUARD_REQUIRED', 'Netzsperre fehlt/abweichend. Ausschliesslich ueber netguard.py run starten; kein ungeschuetzter Fallback.')


def parse_status(data, source, version=4):
    if not isinstance(data, dict) or data.get('error'):
        raise ValueError('Ungueltiger Status')
    ip = ipaddress.ip_address(data.get('ip', ''))
    if ip.version != version or not ip.is_global:
        raise ValueError('Keine passende oeffentliche IP')
    country_code = data.get('country_code') or ''
    country = (data.get('country_name') if source == 'ipapi.co' else data.get('country')) or data.get('country') or ''
    org = data.get('org') if source == 'ipapi.co' else data.get('organization')
    if not isinstance(country_code, str) or (country_code and not re.fullmatch('[A-Za-z]{2}', country_code)):
        raise ValueError('Ungueltiger Laendercode')
    if country_code and country_code.upper() not in ISO_COUNTRIES:
        raise ValueError('Unbekannter Laendercode')
    if not isinstance(country, str) or not (country_code or country.strip()) or not isinstance(org, str) or not org.strip():
        raise ValueError('Land/Organisation fehlt')
    if not country_code and (country.strip().casefold() in {'unknown', 'unbekannt', 'n/a', 'none', 'null', 'undefined', '-', '?'} or not any(c.isalpha() for c in country)):
        raise ValueError('Unbrauchbare Laenderangabe')
    blacklist = data.get('blacklisted')
    if isinstance(blacklist, dict) and blacklist.get('blacklisted') is True:
        print('WARNUNG: Mullvad-Blacklist: ' + safe_text(json.dumps(blacklist.get('results', []), ensure_ascii=False)))
    return {'ip': str(ip), 'country_code': country_code.upper(), 'country': country, 'org': org, 'source': source}


class Network:
    def __init__(self, config, runner, force=False, skip=False):
        self.c, self.r, self.force, self.skip = config, runner, force, skip

    def json_request(self, url, version=4):
        r = self.r.run([CURL, '--disable', '--silent', '--show-error', '--fail', '--max-time', '10',
                        '--connect-timeout', '5', '--noproxy', '*', f'-{version}', '--proto', '=https',
                        '--max-filesize', '1048576', url], timeout=12)
        if r.code != 0 or r.timed_out:
            raise ValueError('Status-Endpunkt antwortet nicht')
        return json.loads(r.out)

    def status(self):
        for attempt in range(3):
            try:
                return parse_status(self.json_request('https://am.i.mullvad.net/json'), 'am.i.mullvad.net')
            except (ValueError, TypeError):
                if attempt < 2:
                    time.sleep(2)
        print('Status-Fallback: Quelle ipapi.co (Mullvad nach drei Versuchen unbrauchbar).')
        try:
            return parse_status(self.json_request('https://ipapi.co/json/'), 'ipapi.co')
        except (ValueError, TypeError):
            fail(2, 'TUNNEL_STATUS_UNAVAILABLE', 'Mullvad und einmaliger ipapi.co-Fallback ohne brauchbaren Status.')

    def policy(self, info, label, allow_force=True):
        print(f'{label}: IP {info["ip"]} | {safe_text(info["country"])} | {safe_text(info["org"])} | Quelle {info["source"]}')
        code, country = info['country_code'], info['country']
        if not code and not country:
            fail(2, 'IP_COUNTRY_UNKNOWN', f'{label}: Land fehlt.')
        if (code == self.c['home_country']) if code else (country.casefold() in {s.casefold() for s in self.c['home_country_names']}):
            fail(2, 'HOME_COUNTRY_DETECTED', f'{label}: Heimatland erkannt.')
        if any(re.search(p, info['org'], re.I) for p in self.c['blocked_orgs']):
            fail(2, 'BLOCKED_ORG', f'{label}: Organisation blockiert.')
        if not any(re.search(p, info['org'], re.I) for p in self.c['allowed_patterns']):
            if self.force and allow_force:
                print('WARNUNG: --force umgeht nur die Organisations-Positivliste fuer IPv4/DNS.')
            else:
                fail(2, 'ORG_NOT_ALLOWLISTED', f'{label}: Organisation nicht auf Positivliste.')

    def dns(self):
        name, visited = 'o-o.myaddr.l.google.com', set()
        for _ in range(8):
            if name in visited:
                break
            visited.add(name)
            r = self.r.run([DIG, '+time=3', '+tries=1', '+noall', '+answer', '+comments', name, 'TXT'], timeout=8)
            if r.code != 0 or r.timed_out or 'status: NOERROR' not in r.out:
                fail(2, 'DNS_RESOLVER_FAILED', 'Systemresolver-TXT-Abfrage fehlgeschlagen.')
            alias, ips = None, set()
            for line in r.out.splitlines():
                if line.startswith(';'):
                    continue
                parts = line.split(None, 4)
                if len(parts) != 5:
                    continue
                if parts[3] == 'CNAME':
                    alias = parts[4].rstrip('.')
                    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,253}', alias):
                        fail(2, 'DNS_CNAME_INVALID', 'Ungueltiger CNAME.')
                if parts[3] == 'TXT':
                    for txt in re.findall(r'"([^"\\]*)"', parts[4]):
                        try:
                            ip = ipaddress.ip_address(txt.strip())
                            if ip.is_global:
                                ips.add(str(ip))
                        except ValueError:
                            pass
            if len(ips) == 1:
                resolver = ips.pop()
                print('DNS: sichtbar rekursiver Ausgang: ' + resolver)
                try:
                    # Exactly one geolocation request per checkpoint.
                    data = self.json_request(f'https://ipapi.co/{resolver}/json/')
                    info = parse_status(data, 'ipapi.co', ipaddress.ip_address(resolver).version)
                    if info['ip'] != resolver:
                        raise ValueError('Falsche Resolver-IP in Geodaten')
                except (ValueError, TypeError):
                    fail(2, 'DNS_GEO_FAILED', 'Keine brauchbaren Resolver-Geodaten.')
                self.policy(info, 'DNS')
                return resolver
            if ips:
                fail(2, 'DNS_RESOLVER_AMBIGUOUS', 'Mehrere rekursive Ausgaenge; keine eindeutige Pruefung.')
            if not alias:
                break
            name = alias
        fail(2, 'DNS_RESOLVER_INVALID', 'Kein eindeutiger oeffentlicher TXT-IP-Wert (CNAME maximal acht Schritte).')

    def check(self, label, expected=None):
        try:
            ensure_guard(self.r)
            if self.skip:
                return None
            status = self.status()
            self.policy(status, label)
            print('IPv6: im gesamten Download-Namespace deaktiviert (all/default/lo/wg0 geprueft); kein IPv6-Pfad in diesem Namespace. Host-Netz nicht beurteilt.')
            self.dns()
            if expected and status['ip'] != expected:
                fail(2, 'EXIT_IP_CHANGED', 'Exit-IP geaendert; Ergebnis verwerfen und Original-Seitenlink frisch starten.')
            return status['ip']
        except Failure as exc:
            if exc.code == 2:
                raise
            fail(2, 'NETWORK_CHECK_ERROR', 'Netzwerk-Hilfsprozess fehlgeschlagen.')
        except (ValueError, OSError, TypeError, KeyError):
            fail(2, 'NETWORK_CHECK_ERROR', 'Netzwerkstatus konnte nicht vollstaendig geprueft werden.')


def ydl_common(referer):
    return [YDL, '--ignore-config', '--no-plugin-dirs', '--no-cache-dir', '--no-playlist',
            '--no-js-runtimes', '--no-remote-components', '--proxy', '', '--socket-timeout', '20',
            '--retries', '0', '--fragment-retries', '0', '--extractor-retries', '0', '--file-access-retries', '0',
            '--no-write-info-json', '--no-write-thumbnail', '--no-write-subs', '--no-write-auto-subs',
            '--referer', referer, '--user-agent', UA, '--ffmpeg-location', str(Path(FFMPEG).parent)]


def origin(url):
    p = urllib.parse.urlsplit(valid_url(url))
    return f'{p.scheme}://{p.netloc}/'


def is_voe(url):
    return bool(re.fullmatch('/e/[a-z0-9]+', urllib.parse.urlsplit(url).path))


def probe(config, runner, net, work):
    baseline = net.check('IPv4 vor Probe')
    if not net.skip:
        output = work / 'probe.mp4'
        try:
            r = runner.run(ydl_common(origin(config['probe_url'])) + ['--force-generic-extractor', '--newline',
                           '--no-continue', '-o', str(output), '--', config['probe_url']], timeout=60, live=True, cwd=work)
            if r.code != 0 or r.timed_out:
                fail(2, 'PROBE_FAILED', f'Probe fehlgeschlagen: Exit={r.code}, Timeout={r.timed_out}.')
            if not output.is_file() or output.is_symlink() or output.stat().st_size == 0:
                fail(2, 'PROBE_OUTPUT_INVALID', 'Probe fehlt oder ist leer.')
        except Failure as exc:
            if exc.code == 2:
                raise
            fail(2, 'PROBE_FAILED', 'Probeprozess fehlgeschlagen.')
        finally:
            output.unlink(missing_ok=True)
    return net.check('IPv4 nach Probe', baseline)


def resolve_item(url, manual, config, runner, net, work, baseline):
    valid_url(url)
    if is_voe(url):
        canonical = 'https://voe.sx' + urllib.parse.urlsplit(url).path
        r = runner.run([sys.executable, '-I', str(APP / 'voe_resolver.py'), canonical, json.dumps(config['voe_hosts'])], timeout=120, cwd=work)
        if r.code != 0 or r.timed_out:
            fail(4, 'VOE_RESOLUTION_FAILED', 'VOE-Aufloesung fehlgeschlagen; Hostliste/Erreichbarkeit pruefen.')
        try:
            info = json.loads(r.out)
            media = valid_url(info['url'])
            title = manual or info.get('title') or urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1]
        except (ValueError, KeyError, TypeError):
            fail(4, 'VOE_RESOLUTION_INVALID', 'VOE lieferte keine eindeutige Medienadresse.')
        return {'name': video_name(title), 'media': media, 'referer': 'https://voe.sx/', 'info': None, 'voe': True}
    args = ydl_common(origin(url)) + ['--skip-download', '--dump-single-json', '--', url]
    r = runner.run(args, timeout=120, cwd=work)
    if r.code and 'Unsupported URL' in r.err + r.out:
        net.check('IPv4 vor Generic-Aufloesung', baseline)
        r = runner.run(args[:-2] + ['--force-generic-extractor'] + args[-2:], timeout=120, cwd=work)
    if r.code != 0 or r.timed_out:
        detail = safe_text((r.err + '\n' + r.out)[-2000:]).strip()
        fail(4, 'LINK_RESOLUTION_FAILED', f'Link nicht aufloesbar (yt-dlp Exit={r.code}, Timeout={r.timed_out}): {detail}')
    try:
        info = json.loads(r.out)
        if not info.get('url') and not any(x.get('url') for x in info.get('formats', [])):
            raise ValueError('Keine Medieninformationen')
        if info.get('_type') in ('playlist', 'multi_video'):
            raise ValueError('Keine einzelnen Medieninformationen')
        title = manual or info.get('title') or urllib.parse.urlsplit(url).path.rsplit('/', 1)[-1] or urllib.parse.urlsplit(url).hostname
        return {'name': video_name(title), 'media': None, 'referer': origin(url), 'info': info, 'voe': False}
    except (ValueError, TypeError):
        fail(4, 'LINK_INFO_INVALID', 'Keine brauchbaren einzelnen Medieninformationen.')


def ffprobe(path, runner):
    r = runner.run([FFPROBE, '-v', 'error', '-show_format', '-show_streams', '-show_chapters', '-show_data_hash', 'sha256', '-of', 'json', str(path)], timeout=60, cwd=path.parent)
    if r.code != 0 or r.timed_out:
        fail(5, 'FFPROBE_FAILED', 'ffprobe fehlgeschlagen.')
    try:
        data = json.loads(r.out)
        if not data.get('format') or not data.get('streams'):
            raise ValueError('Format/Streams fehlen')
        return data
    except (ValueError, TypeError):
        fail(5, 'FFPROBE_EMPTY', 'Keine brauchbaren Format-/Streamdaten.')


def container_extension(data):
    names = set(data['format'].get('format_name', '').split(','))
    if names & {'mov', 'mp4'}:
        return '.mp4'
    if 'matroska' in names or names == {'mpegts'}:
        # Native HLS often delivers MPEG-TS. TS itself is never published:
        # remux every selected stream into MKV without transcoding codecs.
        return '.mkv'
    if 'avi' in names:
        return '.avi'
    fail(1, 'CONTAINER_UNSUPPORTED', 'Nicht unterstuetzter Container: ' + ','.join(sorted(names)))


def check_metadata(data):
    extension = container_extension(data)
    if data.get('chapters'):
        fail(5, 'METADATA_CHAPTERS', 'Kapitel sind nicht entfernt.')
    try:
        duration = float(data['format'].get('duration', 0))
    except (ValueError, TypeError):
        duration = 0
    for index, block in enumerate([data['format']] + data['streams']):
        kind = block.get('codec_type') if index else 'format'
        for key, value in block.get('tags', {}).items():
            tag = key.lower()
            ok = False
            if tag == 'language':
                ok = kind in ('video', 'audio', 'subtitle', 'attachment') and value == 'und'
            elif tag == 'handler_name':
                ok = extension in ('.mp4', '.mkv') and value == {'video': 'VideoHandler', 'audio': 'SoundHandler', 'subtitle': 'SubtitleHandler'}.get(kind)
            elif extension == '.mp4' and kind == 'format':
                allowed = {'major_brand': {'isom', 'mp42', 'mp41'}, 'minor_version': {'0', '512'},
                           'compatible_brands': {'isomiso2avc1mp41', 'isomiso2mp41', 'isomiso2avc1mp41av01', 'mp42mp41isom'}}
                ok = value in allowed.get(tag, set())
            if extension == '.mkv':
                if tag == 'encoder':
                    ok = kind == 'format' and value == 'Lavf'
                elif tag == 'duration' and kind in ('video', 'audio', 'subtitle'):
                    match = re.fullmatch(r'(\d{2}):([0-5]\d):([0-5]\d)\.(\d{9})', str(value))
                    if match and math.isfinite(duration):
                        h, m, s, ns = map(int, match.groups())
                        seconds = h*3600 + m*60 + s + ns/1e9
                        ok = 0 <= seconds <= duration + 0.1
                elif kind == 'attachment' and tag in ('filename', 'mimetype'):
                    ok = value == {'filename': 'attachment.bin', 'mimetype': 'application/octet-stream'}[tag]
            if not ok:
                fail(5, 'METADATA_TAGS_NOT_ALLOWED', f'Nicht erlaubter Metadatenwert: {safe_text(key)} (Wert wird nicht protokolliert).')


def selected_streams(data):
    videos = [s for s in data['streams'] if s['codec_type'] == 'video']
    if not videos:
        fail(1, 'VIDEO_STREAM_MISSING', 'Keine Videospur.')
    return [videos[0]] + [s for kind in ('audio', 'subtitle', 'attachment') for s in data['streams'] if s['codec_type'] == kind]


def verify_streams(before, after):
    expected, actual = selected_streams(before), after['streams']
    if len(expected) != len(actual):
        fail(5, 'STREAMS_LOST', 'Anzahl der Video-/Audio-/Untertitel-/Anhangsspuren abweichend.')
    for a, b in zip(expected, actual):
        if a.get('codec_type') == b.get('codec_type') == 'attachment':
            # Neutral filename/MIME can change ffprobe's inferred attachment codec.
            # Preserve and compare the actual attachment bytes instead.
            if not a.get('extradata_hash') or a.get('extradata_hash') != b.get('extradata_hash') or a.get('extradata_size') != b.get('extradata_size'):
                fail(5, 'ATTACHMENT_CHANGED', 'Anhangsinhalt konnte nicht unveraendert nachgewiesen werden.')
            continue
        if any(a.get(k) != b.get(k) for k in ('codec_type', 'codec_name')):
            fail(5, 'STREAMS_CHANGED', 'Streamtyp oder Codec abweichend; kein stilles Weglassen erlaubt.')


def remux(raw, runner):
    before = ffprobe(raw, runner)
    selected_streams(before)
    extension = container_extension(before)
    clean = raw.parent / ('clean' + extension)
    args = [FFMPEG, '-nostdin', '-v', 'warning', '-n', '-i', str(raw),
            '-map', '0:v:0', '-map', '0:a?', '-map', '0:s?', '-map', '0:t?',
            '-fflags', '+bitexact', '-flags', '+bitexact', '-map_metadata', '-1', '-map_metadata:s', '-1',
            '-map_chapters', '-1', '-metadata', 'encoder=', '-metadata:s', 'encoder=',
            '-metadata:s', 'language=und', '-metadata:s:v', 'handler_name=VideoHandler',
            '-metadata:s:a', 'handler_name=SoundHandler', '-metadata:s:s', 'handler_name=SubtitleHandler',
            '-metadata:s:t', 'filename=attachment.bin', '-metadata:s:t', 'mimetype=application/octet-stream',
            '-c', 'copy', str(clean)]
    r = runner.run(args, timeout=1200, live=True, cwd=raw.parent)
    if r.code != 0 or r.timed_out or not clean.is_file() or clean.stat().st_size == 0:
        fail(5, 'FFMPEG_FAILED', 'Remux fehlgeschlagen (Stream/Container unvertraeglich oder Timeout).')
    after = ffprobe(clean, runner)
    check_metadata(after)
    verify_streams(before, after)
    return clean, extension


def transfer(item, config, runner, net, work, baseline):
    if item['voe'] and (item['referer'] != 'https://voe.sx/' or not UA):
        fail(1, 'VOE_HEADERS_MISSING', 'VOE-Transfer ohne Pflichtheader verweigert.')
    args = ydl_common(item['referer']) + ['--newline', '--no-continue', '--abort-on-unavailable-fragments',
            '--hls-prefer-native', '--fixup', 'never', '--merge-output-format', 'mkv', '-o', str(work / 'raw.%(ext)s'),
            '--print-to-file', 'after_move:filepath', str(work / 'result-path.txt')]
    if item['info'] is not None:
        info_file = work / 'media.json'
        with info_file.open('w', encoding='utf-8') as stream:
            json.dump(item['info'], stream)
        # The private info file is already required for --load-info-json/retry.
        # Release Python's format/URL graph before the long transfer starts.
        item['info'] = None
        args += ['--load-info-json', str(info_file)]
    else:
        args += ['--force-generic-extractor', '--', item['media']]
    fast = ['--http-chunk-size', '10M', '--concurrent-fragments', '4']
    for attempt in range(2):
        # Remove ALL previous attempt files, never resume a damaged partial transfer.
        for old in work.iterdir():
            if old.name.startswith('raw.') or old.name == 'result-path.txt':
                if not old.is_file() or old.is_symlink():
                    fail(4, 'PARTIAL_UNSAFE', 'Unsicherer Teilstand.')
                old.unlink()
        net.check('IPv4 unmittelbar vor Transfer' if not attempt else 'IPv4 vor kompatiblem Retry', baseline)
        # No external preparatory operations between this checkpoint and transfer.
        current = args[:1] + (fast if not attempt else []) + args[1:]
        result = runner.run(current, timeout=config['download_timeout_sec'], live=True, cwd=work)
        if result.code == 0 and not result.timed_out:
            try:
                lines = (work / 'result-path.txt').read_text().splitlines()
                if len(lines) != 1:
                    raise ValueError('Kein eindeutiger Dateipfad')
                raw = Path(lines[0])
                if not raw.is_absolute():
                    raw = work / raw
                if raw.parent != work or raw.is_symlink() or not raw.name.startswith('raw.') or not raw.is_file() or raw.stat().st_size == 0:
                    raise ValueError('Unbrauchbare Rohdatei')
                return raw
            except (OSError, ValueError):
                fail(4, 'DOWNLOAD_OUTPUT_INVALID', 'Erfolgreicher Exit ohne eindeutige nichtleere Rohdatei.')
        if attempt == 0:
            print('WARNUNG: Transfer fehlgeschlagen; einmal frisch ohne HTTP-Chunks/parallele Fragmente.')
    fail(4, 'DOWNLOAD_FAILED', f'yt-dlp fehlgeschlagen: Exit={result.code}, Timeout={result.timed_out}.')


def download(url, manual, config, runner, net, store):
    with store.workspace() as work:
        baseline = probe(config, runner, net, work)
        item = resolve_item(url, manual, config, runner, net, work, baseline)
        print('Name: ' + safe_text(item['name']))
        raw = transfer(item, config, runner, net, work, baseline)
        clean, extension = remux(raw, runner)
        post = net.check('IPv4 nach Transfer/Remux', baseline)
        target = store.publish(clean, item['name'], extension)
        if post:
            store.last_ip(post)
        print('Fertig: ' + str(target))
        return target


def run_queue(entries, execute):
    ok = skipped = aborted = 0
    code = 0
    for i, entry in enumerate(entries):
        if not entry['valid']:
            skipped += 1
            code = 1
            continue
        try:
            execute(entry, i+1, len(entries))
            ok += 1
        except Failure as exc:
            error(exc)
            if exc.code == 2:
                aborted = len(entries)-i
                code = 2
                break
            skipped += 1
            code = 1
        except KeyboardInterrupt:
            aborted = len(entries)-i
            code = 1
            break
    print(f'Warteschlange: {ok} erfolgreich, {skipped} übersprungen, {aborted} abgebrochen')
    return code


def interactive(config, runner, net, store, manual=None):
    urls = []
    print('Ein HTTP/HTTPS-Link pro Zeile; leere Zeile, fertig oder ende beendet die Eingabe.')
    while True:
        line = input(f'Link {len(urls)+1}: ').strip()
        if not line or line.casefold() in ('fertig', 'ende'):
            break
        try:
            valid_url(line)
            urls.append(line)
        except ValueError:
            print('Ungueltiger Link; vollstaendige HTTP/HTTPS-Adresse erforderlich.')
    if not urls:
        print('Warteschlange: 0 erfolgreich, 0 übersprungen, 0 abgebrochen')
        return 0
    entries = []
    try:
        with store.workspace() as work:
            baseline = probe(config, runner, net, work)
            for i, url in enumerate(urls):
                print(f'Pruefe Link {i+1}/{len(urls)}...')
                try:
                    # Recheck per preview item too, since input/requests can take time.
                    net.check('IPv4 vor Vorschau-Eintrag', baseline)
                    item = resolve_item(url, f'{manual}_{i+1}' if manual else None, config, runner, net, work, baseline)
                    entries.append({'url': url, 'name': item['name'], 'valid': True})
                    # Retain only names and original URLs, never signed media info.
                    del item
                except Failure as exc:
                    if exc.code == 2:
                        raise
                    entries.append({'url': url, 'name': '', 'valid': False, 'error': safe_text(exc)})
            net.check('IPv4 nach Vorschau', baseline)
    except Failure as exc:
        error(exc)
        print(f'Warteschlange: 0 erfolgreich, 0 übersprungen, {len(urls)} abgebrochen')
        return exc.code
    for i, item in enumerate(entries):
        print(f'{i+1}. ' + ('OK: ' + safe_text(item['name']) if item['valid'] else 'FEHLER: ' + item['error']))
    if not any(x['valid'] for x in entries):
        return run_queue(entries, lambda *a: None)
    while True:
        answer = input('Enter startet; abbrechen verwirft die Liste: ').strip().casefold()
        if answer == 'abbrechen':
            print(f'Warteschlange: 0 erfolgreich, 0 übersprungen, {len(entries)} abgebrochen')
            return 0
        if not answer:
            break
        print('Bitte Enter oder abbrechen eingeben.')
    def execute(item, index, total):
        runner.position = (index, total)
        download(item['url'], item['name'], config, runner, net, store)
    return run_queue(entries, execute)


def main(argv=None):
    parser = argparse.ArgumentParser(description='PiGrab — nur im geschuetzten Download-Namespace.')
    parser.add_argument('url', nargs='?')
    parser.add_argument('name', nargs='?')
    parser.add_argument('--config', default=str(APP / 'config.toml'))
    parser.add_argument('--force', action='store_true', help='SICHTBARE AUSNAHME: IPv4-/DNS-Organisationspositivliste umgehen; keine Heimatland-/Blocklist-/Netzsperren-Ausnahme.')
    parser.add_argument('--skip-check', action='store_true', help='SICHTBARE AUSNAHME: IP/DNS/Probe/Stabilitaetskontrollen auslassen; Namespace-Sperre bleibt Pflicht.')
    args = parser.parse_args(argv)
    try:
        if sys.platform != 'linux':
            fail(1, 'PLATFORM_UNSUPPORTED', 'Produktiver Start nur unter Linux. Keine Windows-Installation veraendert.')
        os.umask(0o077)
        runner = Runner()
        ensure_guard(runner)
        config = load_config(args.config)
        if args.force:
            print('WARNUNG: --force aktiv: nur IPv4-/DNS-Organisationspositivliste wird umgangen.')
        if args.skip_check:
            print('WARNUNG: --skip-check aktiv: KEINE IP/DNS/Probe/IP-Stabilitaetspruefung; Netzsperre weiterhin zwingend.')
        net = Network(config, runner, args.force, args.skip_check)
        store = Store(config['storage'])
        store.cleanup()
        if args.url:
            try:
                valid_url(args.url)
            except ValueError:
                fail(1, 'INPUT_URL_INVALID', 'Ungueltige HTTP/HTTPS-URL.')
            download(args.url, args.name, config, runner, net, store)
            return 0
        return interactive(config, runner, net, store, args.name)
    except Failure as exc:
        error(exc)
        return exc.code
    except (KeyboardInterrupt, EOFError):
        error(Failure(1, 'USER_ABORT', 'Durch Benutzer/Eingabeende abgebrochen.'))
        return 1
    except Exception as exc:
        error(Failure(1, 'UNEXPECTED_ERROR', f'Unerwarteter Fehler ({type(exc).__name__}); kein Erfolg gemeldet.'))
        return 1


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    sys.exit(main())
