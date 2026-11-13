import contextlib
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import weakref
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grab as g
import voe_resolver as voe

CONFIG = g.load_config(Path(g.__file__).with_name('config.toml'))


class TestCore(unittest.TestCase):
    def test_unicode_and_shell_characters(self):
        name = g.video_name('Watch Grüße & $(touch pwned); `whoami`.mp4 | VOE')
        self.assertIn('Grüße_&_', name)
        self.assertIn('$(touch_pwned)', name)
        self.assertNotIn('/', g.video_name('../../etc/passwd'))
        self.assertLessEqual(len(g.video_name('😀'*120).encode('utf-8')), 220)

    def test_url_input(self):
        for url in ('file:///etc/passwd', 'https://u:p@example.com/x', 'https://x/\r\nHeader:x', '--exec=whoami'):
            with self.assertRaises(ValueError):
                voe.valid_url(url)
        self.assertTrue(g.is_voe('https://any-host.example/e/abc123'))

    def test_policy_and_missing_country(self):
        data = {'ip': '1.1.1.1', 'country': 'Germany', 'organization': 'Proton'}
        net = g.Network(CONFIG, None, force=True)
        with self.assertRaises(g.Failure) as caught:
            net.policy(g.parse_status(data, 'am.i.mullvad.net'), 'Test')
        self.assertEqual(caught.exception.code, 2)
        data['country'] = 'France'
        data['organization'] = 'Vodafone Proton'
        with self.assertRaises(g.Failure):
            net.policy(g.parse_status(data, 'am.i.mullvad.net'), 'Test')
        del data['country']
        with self.assertRaises(ValueError):
            g.parse_status(data, 'am.i.mullvad.net')

    def test_current_mullvad_shape(self):
        info = g.parse_status({'ip': '1.1.1.1', 'country': 'The Netherlands', 'organization': 'WorldStream B.V.',
                               'blacklisted': {'blacklisted': False, 'results': []}}, 'am.i.mullvad.net')
        self.assertEqual(info['country_code'], '')
        self.assertEqual(info['org'], 'WorldStream B.V.')
        for value in ('127.0.0.1', 'not-an-ip', '192.168.1.2'):
            with self.assertRaises(ValueError):
                g.parse_status({'ip': value, 'country': 'NL', 'organization': 'Proton'}, 'am.i.mullvad.net')
        for country in ({'country_code':'ZZ'}, {'country':'Unknown'}, {'country':'--'}):
            with self.assertRaises(ValueError):
                g.parse_status({'ip':'1.1.1.1','organization':'Proton',**country},'am.i.mullvad.net')

    def test_fallback_exactly_three_plus_one(self):
        net = g.Network(CONFIG, None)
        calls = []
        def request(url, version=4):
            calls.append(url)
            if 'mullvad' in url:
                raise ValueError('simulated outage')
            return {'ip': '1.1.1.1', 'country_code': 'NL', 'country_name': 'Netherlands', 'org': 'Proton'}
        net.json_request = request
        with patch.object(g.time, 'sleep'):
            self.assertEqual(net.status()['source'], 'ipapi.co')
        self.assertEqual(len(calls), 4)
        net.json_request = lambda *a: {}
        with patch.object(g.time, 'sleep'), self.assertRaises(g.Failure) as caught:
            net.status()
        self.assertEqual(caught.exception.code, 2)

    def test_dns_cname_and_single_geo(self):
        class Fake:
            def __init__(self):
                self.n = 0
            def run(self, *a, **kw):
                self.n += 1
                txt = 'x 30 IN CNAME alias.example.' if self.n == 1 else 'alias.example. 20 IN TXT "1.1.1.1"'
                return g.Result(0, ';; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1\n'+txt)
        net = g.Network(CONFIG, Fake())
        count = []
        def geo(url, version=4):
            count.append(url)
            return {'ip': '1.1.1.1', 'country_code': 'NL', 'org': 'Proton'}
        net.json_request = geo
        self.assertEqual(net.dns(), '1.1.1.1')
        self.assertEqual(len(count), 1)

    def test_ip_change_blocks(self):
        net = g.Network(CONFIG, None)
        net.status = lambda: {'ip': '1.1.1.1', 'country_code': 'NL', 'country': 'NL', 'org': 'Proton', 'source': 'test'}
        net.dns = lambda: '1.1.1.2'
        with patch.object(g, 'ensure_guard'), self.assertRaises(g.Failure) as caught:
            net.check('Test', '8.8.8.8')
        self.assertEqual(caught.exception.ident, 'EXIT_IP_CHANGED')

    def test_network_process_failure_is_fatal(self):
        net = g.Network(CONFIG, None)
        net.status = lambda: g.fail(1, 'PROCESS_START_FAILED', 'test')
        with patch.object(g, 'ensure_guard'), self.assertRaises(g.Failure) as caught:
            net.check('test')
        self.assertEqual(caught.exception.code, 2)

    def test_metadata_values_not_only_names(self):
        for container in ('mov,mp4,m4a,3gp,3g2,mj2', 'matroska,webm'):
            data = {'format': {'format_name': container, 'duration': '2'}, 'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'tags': {}}]}
            g.check_metadata(data)
            for tag in ('encoder', 'handler_name', 'language', 'duration', 'filename'):
                test = copy.deepcopy(data)
                test['streams'][0]['tags'] = {tag: 'tracking-123'}
                with self.assertRaises(g.Failure) as caught:
                    g.check_metadata(test)
                self.assertEqual(caught.exception.code, 5)
        for duration in ('00:00:20.000000000', '99:99:99.000000000'):
            data = {'format': {'format_name': 'matroska,webm', 'duration': '2'}, 'streams': [{'codec_type': 'video', 'tags': {'DURATION': duration}}]}
            with self.assertRaises(g.Failure):
                g.check_metadata(data)

    def test_stream_loss_rejected(self):
        data = {'streams': [{'codec_type': 'video', 'codec_name': 'h264'}, {'codec_type': 'audio', 'codec_name': 'aac'}, {'codec_type': 'subtitle', 'codec_name': 'subrip'}, {'codec_type': 'attachment', 'codec_name': 'ttf'}]}
        with self.assertRaises(g.Failure):
            g.verify_streams(data, {'streams': data['streams'][:-1]})

    def test_queue_semantics(self):
        entries = [{'valid': True} for _ in range(3)]
        out = io.StringIO()
        def mixed(item, index, total):
            if index < 3:
                g.fail(4 if index == 1 else 5, 'SIMULATED', 'Fehler')
        with contextlib.redirect_stdout(out):
            self.assertEqual(g.run_queue(entries, mixed), 1)
        self.assertIn('1 erfolgreich, 2 übersprungen, 0 abgebrochen', out.getvalue())
        seen = []
        def fatal(item, index, total):
            seen.append(index)
            g.fail(2, 'SIMULATED', 'Netzfehler')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(g.run_queue(entries, fatal), 2)
        self.assertEqual(seen, [1])

    def test_failed_probe_never_resolves(self):
        with tempfile.TemporaryDirectory() as d:
            store = g.Store(d)
            with patch.object(g, 'probe', side_effect=g.Failure(2, 'PROBE_FAILED', 'test')), patch.object(g, 'resolve_item') as resolve:
                with self.assertRaises(g.Failure):
                    g.download('https://example.com/x', None, CONFIG, None, None, store)
                resolve.assert_not_called()
            self.assertEqual(list(store.work.iterdir()), [])

    def test_probe_hard_deadline_exit_and_empty_file(self):
        class Net:
            skip=False
            def check(self,*a): return '1.1.1.1'
        for result,create in [(g.Result(7,''),True),(g.Result(0,''),False),(g.Result(-9,'',timed_out=True),True)]:
            class Fake:
                def run(self,args,**kwargs):
                    self.timeout=kwargs['timeout']
                    if create: (kwargs['cwd']/'probe.mp4').write_bytes(b'x')
                    return result
            with tempfile.TemporaryDirectory() as d:
                fake=Fake()
                with self.assertRaises(g.Failure) as caught:
                    g.probe(CONFIG,fake,Net(),Path(d))
                self.assertEqual(caught.exception.code,2)
                self.assertEqual(fake.timeout,60)
                self.assertFalse((Path(d)/'probe.mp4').exists())

    def test_postcheck_blocks_publication(self):
        class Net:
            def check(self, *a):
                g.fail(2, 'EXIT_IP_CHANGED', 'simulated')
        with tempfile.TemporaryDirectory() as d:
            store = g.Store(d)
            def fake_remux(raw, runner):
                raw.write_bytes(b'video')
                return raw, '.mp4'
            with patch.object(g, 'probe', return_value='1.1.1.1'), patch.object(g, 'resolve_item', return_value={'name': 'Test'}), \
                 patch.object(g, 'transfer', side_effect=lambda i,c,r,n,w,b: w/'clean.mp4'), patch.object(g, 'remux', side_effect=fake_remux):
                with self.assertRaises(g.Failure):
                    g.download('https://example.com/x', None, CONFIG, None, Net(), store)
            self.assertEqual(list(store.output.iterdir()), [])
            self.assertFalse((store.state / '.last_exit_ip').exists())

    def test_atomic_collision_and_cleanup(self):
        with tempfile.TemporaryDirectory() as d:
            store = g.Store(d)
            with store.workspace() as work:
                raw = work / 'clean.mp4'
                raw.write_bytes(b'one')
                self.assertEqual(store.publish(raw, 'Grüße', '.mp4').name, 'Grüße.mp4')
                raw.write_bytes(b'two')
                self.assertEqual(store.publish(raw, 'Grüße', '.mp4').name, 'Grüße_2.mp4')
            self.assertEqual((store.output / 'Grüße.mp4').read_bytes(), b'one')
            self.assertEqual(list(store.work.iterdir()), [])
            old = store.work / ('a'*32)
            old.mkdir()
            (old / 'raw').write_bytes(b'x')
            past = time.time() - 90000
            os.utime(old, (past, past))
            self.assertEqual(store.cleanup(), 1)

    @unittest.skipUnless(os.name == 'posix', 'Linux-flock/Symlink-Abwehr benoetigt Linux')
    def test_active_and_symlink_work_not_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            store = g.Store(d)
            with store.workspace() as work:
                past = time.time() - 90000
                os.utime(work, (past, past))
                store.cleanup()
                self.assertTrue(work.exists())
            old = store.work / ('b'*32)
            old.mkdir()
            (old / 'escape').symlink_to(store.output, target_is_directory=True)
            os.utime(old, (past, past))
            self.assertEqual(store.cleanup(), 0)

    def test_native_exit_timeout_and_no_shell(self):
        runner = g.Runner()
        result = runner.run([sys.executable, '-c', 'import sys; print(sys.argv[1]); sys.exit(7)', 'Grüße & $(touch pwned); `whoami`'])
        self.assertEqual(result.code, 7)
        self.assertIn('$(touch pwned)', result.out)
        start = time.monotonic()
        result = runner.run([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=0.2)
        self.assertTrue(result.timed_out)
        self.assertNotEqual(result.code, 0)
        self.assertLess(time.monotonic()-start, 5)

    def test_live_output_is_visible_without_retained_copy(self):
        class Sink:
            count=0
            def write(self,text): self.count += len(text); return len(text)
            def flush(self): pass
        sink=Sink()
        with contextlib.redirect_stdout(sink):
            result=g.Runner().run([sys.executable,'-c','import sys; sys.stdout.write("progress line\\n"*40000); sys.stderr.write("warning\\n")'],live=True)
        self.assertEqual(result.code,0)
        self.assertGreater(sink.count,500000)
        self.assertEqual((result.out,result.err),('',''))

    def test_info_memory_released_but_retry_file_preserved(self):
        class Info(dict): pass
        info=Info(url='https://cdn.example/video.mp4?token=private',title='Grüße')
        reference=weakref.ref(info)
        item={'voe':False,'referer':'https://example.com/','info':info,'media':None}
        del info
        calls=[]
        class Net:
            def check(inner,*args):
                self.assertIsNone(reference())
        class Fake:
            def run(inner,args,**kw):
                self.assertIsNone(reference())
                path=Path(args[args.index('--load-info-json')+1])
                calls.append(json.loads(path.read_text()))
                if len(calls)==1:
                    return g.Result(1,'','Range error')
                raw=kw['cwd']/'raw.mp4'
                raw.write_bytes(b'valid')
                (kw['cwd']/'result-path.txt').write_text(str(raw)+'\n')
                return g.Result(0,'')
        with tempfile.TemporaryDirectory() as d:
            g.transfer(item,CONFIG,Fake(),Net(),Path(d),'1.1.1.1')
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0],calls[1])
        self.assertEqual(calls[1]['title'],'Grüße')

    def test_retry_is_fresh_and_headers(self):
        checks = []
        class Net:
            def check(self, *a): checks.append(a)
        class Fake:
            def __init__(self): self.calls = []
            def run(self, args, **kw):
                self.calls.append(args)
                work = kw['cwd']
                if len(self.calls) == 1:
                    (work / 'raw.mp4.part').write_bytes(b'broken')
                    return g.Result(1, '', 'HTTP 416 Range')
                assert not (work / 'raw.mp4.part').exists()
                raw = work / 'raw.mp4'
                raw.write_bytes(b'valid')
                (work / 'result-path.txt').write_text(str(raw)+'\n')
                return g.Result(0, '')
        item = {'voe': True, 'referer': 'https://voe.sx/', 'info': None, 'media': 'https://cdn.example/x.mp4?token=secret'}
        with tempfile.TemporaryDirectory() as d:
            fake = Fake()
            g.transfer(item, CONFIG, fake, Net(), Path(d), '1.1.1.1')
        self.assertEqual(len(checks), 2)
        self.assertIn('--http-chunk-size', fake.calls[0])
        self.assertNotIn('--http-chunk-size', fake.calls[1])
        self.assertNotIn('--concurrent-fragments', fake.calls[1])
        for args in fake.calls:
            self.assertEqual(args[args.index('--referer')+1], 'https://voe.sx/')
            self.assertEqual(args[args.index('--user-agent')+1], g.UA)

    def test_voe_fixture_and_redirect_restriction(self):
        page = '<html><meta property="og:title" content="Watch Grüße.mp4 | VOE"><script>sources = {"mp4":"https://cdn.example/film.mp4?token=abc"}</script></html>'
        result = voe.parse_page(page, 'https://voe.sx/e/abc')
        self.assertEqual(result['title'], 'Watch Grüße.mp4 | VOE')
        self.assertIn('token=abc', result['url'])
        with self.assertRaises(ValueError):
            voe.allowed_page('https://evil.example/e/a', ['voe.sx'])

    def test_preview_protects_order_and_passes_only_names(self):
        events=[]
        class Net:
            def check(self,*a): events.append('check'); return '1.1.1.1'
        def first_probe(*a): events.append('probe'); return '1.1.1.1'
        def resolve(url,manual,*args):
            events.append('resolve')
            if 'bad' in url: g.fail(4,'BAD_LINK','Simulierter Linkfehler')
            return {'name':'Grüße','media':'https://cdn.example/?token=must-not-reuse'}
        calls=[]
        def download(url,name,*args): calls.append((url,name))
        with tempfile.TemporaryDirectory() as d:
            store=g.Store(d)
            with patch.object(g,'probe',side_effect=first_probe), patch.object(g,'resolve_item',side_effect=resolve), \
                 patch.object(g,'download',side_effect=download), patch('builtins.input',side_effect=['https://example.com/good','https://example.com/bad','fertig','']), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g.interactive(CONFIG,g.Runner(),Net(),store),1)
            self.assertEqual(events[0],'probe')
            self.assertEqual(calls,[('https://example.com/good','Grüße')])
            self.assertEqual(list(store.work.iterdir()),[])


if __name__ == '__main__':
    unittest.main(verbosity=2)
