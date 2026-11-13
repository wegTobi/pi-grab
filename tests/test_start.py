import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import start


class TestStart(unittest.TestCase):
    def test_user_arguments_stay_separate_and_guarded(self):
        args=['https://example.com/e/abc?token=a&x=$(whoami)','Grüße; `touch anything`']
        argv=start.command('alice',args)
        self.assertEqual(argv[:4],['/usr/bin/sudo','--','/opt/pi-grab/venv/bin/python','-I'])
        self.assertEqual(argv[4:9],['/opt/pi-grab/netguard.py','run','--user','alice','--'])
        self.assertEqual(argv[9:],args)
        self.assertNotIn('--skip-check',argv)

    def test_root_is_refused_before_sudo(self):
        with patch.object(start.sys,'platform','linux'), patch.object(start.os,'getuid',return_value=0,create=True), \
             patch.object(start.os,'geteuid',return_value=0,create=True), patch.object(start.os,'execv') as execute, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(start.main([]),1)
            execute.assert_not_called()

    def test_help_needs_no_root_or_network(self):
        with patch.object(start.os,'execv') as execute, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(start.main(['--help']),0)
            self.assertIn('Warteschlange',output.getvalue())
            execute.assert_not_called()
