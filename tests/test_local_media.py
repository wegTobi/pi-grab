"""Real local HTTP/FFmpeg tests, simulated VPN checks. NEVER a VPN proof."""
import concurrent.futures
import contextlib
import functools
import http.server
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grab as g

FFMPEG = os.environ.get('PIGRAB_TEST_FFMPEG', '/usr/bin/ffmpeg')
FFPROBE = os.environ.get('PIGRAB_TEST_FFPROBE', '/usr/bin/ffprobe')
YDL = os.environ.get('PIGRAB_TEST_YDL', str(Path(g.__file__).parent / 'venv/bin/yt-dlp'))
AVAILABLE = all(Path(p).is_file() for p in (FFMPEG, FFPROBE, YDL))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class SimulatedVPN:
    skip = False
    def __init__(self): self.calls = []
    def check(self, label, expected=None):
        self.calls.append(label)
        return '1.1.1.1'


def publish_worker(args):
    base,index=args
    store=g.Store(base)
    with store.workspace() as work:
        raw=work/'clean.mp4'
        raw.write_bytes(str(index).encode())
        return str(store.publish(raw,'Gleich','.mp4'))


@unittest.skipUnless(AVAILABLE, 'Lokale Test-Binaries fehlen; PIGRAB_TEST_* setzen')
class TestMedia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.site = cls.root / 'site'
        cls.site.mkdir()
        cls.saved = (g.YDL, g.FFMPEG, g.FFPROBE)
        g.YDL, g.FFMPEG, g.FFPROBE = YDL, FFMPEG, FFPROBE
        cls.make(['-f','lavfi','-i','testsrc2=size=160x90:rate=10:duration=2',
                  '-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(cls.site/'sample.mp4')])
        cls.make(['-i',str(cls.site/'sample.mp4'),'-c','copy','-f','hls','-hls_time','1','-hls_list_size','0',str(cls.site/'index.m3u8')])
        cls.server = http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(Quiet, directory=str(cls.site)))
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def make(cls, args):
        p=subprocess.run([FFMPEG,'-nostdin','-v','error','-y']+args, capture_output=True, timeout=30)
        if p.returncode:
            raise AssertionError(p.stderr.decode(errors='replace'))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        g.YDL,g.FFMPEG,g.FFPROBE=cls.saved
        cls.temp.cleanup()

    def config(self):
        config=g.load_config(Path(g.__file__).with_name('config.toml'))
        config['probe_url']=self.base+'/sample.mp4'
        config['download_timeout_sec']=20
        return config

    def test_direct_and_hls_real_local_transfers(self):
        for name,url in [('Grüße & $(whoami)',self.base+'/sample.mp4'),('HLS',self.base+'/index.m3u8')]:
            store=g.Store(self.root/('out-'+g.video_name(name)))
            net=SimulatedVPN()
            with contextlib.redirect_stdout(io.StringIO()):
                target=g.download(url,name,self.config(),g.Runner(),net,store)
            self.assertTrue(target.is_file())
            self.assertGreater(target.stat().st_size,0)
            self.assertEqual(list(store.work.iterdir()),[])
            self.assertTrue((store.state/'.last_exit_ip').is_file())
            self.assertGreaterEqual(len(net.calls),4)

    def test_local_valid_broken_queue(self):
        store=g.Store(self.root/'queue')
        entries=[{'valid':True,'url':self.base+'/sample.mp4'}, {'valid':True,'url':self.base+'/does-not-exist.mp4'}]
        def execute(item,index,total):
            g.download(item['url'],f'Queue{index}',self.config(),g.Runner(),SimulatedVPN(),store)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(g.run_queue(entries,execute),1)
        self.assertEqual(len(list(store.output.iterdir())),1)

    def test_mp4_mkv_avi_remux(self):
        for ext in ('mp4','mkv','avi'):
            directory=self.root/('remux-'+ext)
            directory.mkdir()
            raw=directory/('raw.'+ext)
            self.make(['-i',str(self.site/'sample.mp4'),'-c','copy',str(raw)])
            with contextlib.redirect_stdout(io.StringIO()):
                clean,actual=g.remux(raw,g.Runner())
            self.assertEqual(actual,'.'+ext)
            self.assertTrue(clean.is_file())

    def test_subtitles_attachments_extra_video_and_bad_tags(self):
        directory=self.root/'streams'
        directory.mkdir()
        sub=directory/'private.srt'
        sub.write_text('1\n00:00:00,000 --> 00:00:01,000\nTest\n')
        attachment=directory/'private.bin'
        attachment.write_bytes(b'attachment-data-123')
        raw=directory/'raw.mkv'
        self.make(['-i',str(self.site/'sample.mp4'),'-i',str(sub),'-map','0:v','-map','0:v','-map','0:a','-map','0:a','-map','1:s',
                   '-c','copy','-attach',str(attachment),'-metadata:s:t','mimetype=application/octet-stream',
                   '-metadata','title=PRIVATE','-metadata:s:v','handler_name=tracking-123',str(raw)])
        with contextlib.redirect_stdout(io.StringIO()):
            clean,_=g.remux(raw,g.Runner())
        data=g.ffprobe(clean,g.Runner())
        types=[s['codec_type'] for s in data['streams']]
        self.assertEqual(types.count('video'),1)
        self.assertEqual(types.count('audio'),2)
        self.assertEqual(types.count('subtitle'),1)
        self.assertEqual(types.count('attachment'),1)
        # An actually encoded personalized tag must be refused before publishing.
        malicious=directory/'malicious.mkv'
        self.make(['-i',str(clean),'-map','0','-c','copy','-metadata','encoder=private-id','-metadata:s:v','title=tracking-123',str(malicious)])
        with self.assertRaises(g.Failure) as caught:
            g.check_metadata(g.ffprobe(malicious,g.Runner()))
        self.assertEqual(caught.exception.code,5)

    def test_parallel_publication(self):
        store=g.Store(self.root/'parallel')
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
            paths=list(pool.map(publish_worker,[(str(store.base),i) for i in range(12)]))
        self.assertEqual(len(set(paths)),12)
        self.assertEqual(len(list(store.output.iterdir())),12)
        self.assertEqual(list(store.work.iterdir()),[])


if __name__=='__main__':
    unittest.main(verbosity=2)
