import base64
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import netguard as n


class TestAdmin(unittest.TestCase):
    def profile(self):
        key=base64.b64encode(b'x'*32).decode()
        return f'[Interface]\nPrivateKey={key}\nAddress=10.2.0.2/32, fd00::2/128\nDNS=10.2.0.1\n[Peer]\nPublicKey={key}\nAllowedIPs=0.0.0.0/0, ::/0\nEndpoint=1.1.1.1:51820\n'

    def parse(self,text):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'vpn.conf'
            path.write_text(text)
            with patch.object(n,'trusted_file'):
                return n.parse_profile(path)

    def test_profile_strips_ipv6_and_preserves_no_hooks(self):
        clean,address,dns,mtu=self.parse(self.profile())
        self.assertEqual(address,'10.2.0.2/32')
        self.assertEqual(dns,['10.2.0.1'])
        self.assertNotIn('::/0',clean)
        self.assertNotIn('Address',clean)
        self.assertEqual(mtu,1380)

    def test_hooks_host_dns_and_split_routes_rejected(self):
        examples=[self.profile().replace('DNS=10.2.0.1','DNS=127.0.0.53'),
                  self.profile().replace('DNS=10.2.0.1','DNS=10.2.0.1\nPostUp=touch /tmp/unsafe'),
                  self.profile().replace('AllowedIPs=0.0.0.0/0, ::/0','AllowedIPs=10.0.0.0/8'),
                  self.profile().replace('Endpoint=1.1.1.1:51820','Endpoint=host.example:51820')]
        for text in examples:
            with self.assertRaises(ValueError):
                self.parse(text)

    def test_firewall_default_drop_and_no_physical_interface(self):
        self.assertEqual(n.RULES.count('policy drop'),3)
        self.assertIn('meta nfproto ipv4 oifname "wg0" accept',n.RULES)
        self.assertNotIn('eth0',n.RULES)
        self.assertNotIn('wlan0',n.RULES)


if __name__=='__main__':
    unittest.main(verbosity=2)
