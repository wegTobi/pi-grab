#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Restricted resolver; no eval, JS execution, downloads or debug-page files."""
import base64
import contextlib
import html
import io
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

# -I excludes the script directory; explicitly admit only this installed source.
sys.path.insert(0, str(Path(__file__).resolve().parent))

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0'


def valid_url(url):
    if not isinstance(url, str) or any(ord(c) < 33 for c in url):
        raise ValueError('Ungueltige Medienadresse')
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('Keine erlaubte HTTP/HTTPS-Adresse')
    _ = p.port
    return url


def allowed_page(url, hosts):
    valid_url(url)
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or p.hostname not in hosts or p.port not in (None, 443):
        raise ValueError('VOE-Weiterleitung ausserhalb der konfigurierten HTTPS-Hosts')
    return url


class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        super().__init__()
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed_page(newurl, self.hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def parse_page(text, url):
    from bs4 import BeautifulSoup
    from voe_dl.sources import SOURCE_METHODS
    soup = BeautifulSoup(text, 'html.parser')
    tag = soup.find('meta', attrs={'property': 'og:title'}) or soup.find('meta', attrs={'name': 'og:title'})
    title = tag.get('content', '') if tag else ''
    if not title and soup.title:
        title = soup.title.get_text()
    # Upstream's diagnostics may contain signed URLs: discard in memory.
    with contextlib.redirect_stdout(io.StringIO()):
        for method in SOURCE_METHODS:
            data = method(soup, text, url)
            if not data:
                continue
            if isinstance(data, str):
                data = {'mp4': data}
            for key in ('mp4', 'hls'):
                media = data.get(key)
                if not isinstance(media, str) or not media:
                    continue
                if not media.startswith(('http://', 'https://', '//')):
                    media = base64.b64decode(media, validate=True).decode('utf-8')
                if media.startswith('//'):
                    media = 'https:' + media
                return {'title': html.unescape(title), 'url': valid_url(html.unescape(media))}
    return None


def resolve(url, hosts):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), Redirect(hosts))
    visited = set()
    for _ in range(4):
        allowed_page(url, hosts)
        if url in visited:
            raise ValueError('VOE-Weiterleitungsschleife')
        visited.add(url)
        req = urllib.request.Request(url, headers={'User-Agent': UA, 'Referer': 'https://voe.sx/'})
        with opener.open(req, timeout=20) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('VOE-Seite zu gross')
            text = raw.decode('utf-8', errors='replace')
            url = response.url
        match = re.search(r'''(?:window\.)?location(?:\.href)?\s*=\s*["']([^"']+)["']|(?:window\.)?location\.(?:replace|assign)\(\s*["']([^"']+)["']''', text)
        if match:
            url = urllib.parse.urljoin(url, match.group(1) or match.group(2))
            continue
        result = parse_page(text, url)
        if result:
            return result
        raise ValueError('Keine eindeutige unterstuetzte Medienquelle; keine Schutzumgehung')
    raise ValueError('Zu viele VOE-Weiterleitungen')


if __name__ == '__main__':
    try:
        print(json.dumps(resolve(sys.argv[1], json.loads(sys.argv[2])), ensure_ascii=False))
    except Exception:
        # Never include the signed address or response body in persistent output.
        print('VOE_RESOLUTION_FAILED: Aufloesung fehlgeschlagen (Hostliste/Seitenformat/Erreichbarkeit pruefen).', file=sys.stderr)
        sys.exit(4)
