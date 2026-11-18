import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'device'))
sys.path.insert(0, str(ROOT / 'tools'))
import release
from ota.integrity import manifest, digest, verify_signature, verify_slot, valid_path
from ota.storage import Store, initial_state, choose
from ota.updater import Updater
from ota.http import headers

class Transport:
    def __init__(self, tree, fail=False):
        self.tree, self.fail = tree, fail
    def get(self, path, maximum):
        data = (self.tree / path).read_bytes()
        if len(data) > maximum: raise ValueError('size')
        return data
    def fetch(self, path, maximum, sink):
        data = self.get(path, maximum)
        if self.fail:
            sink(data[:3])
            raise OSError('network interrupted')
        sink(data)

class OTA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.private = cls.base / 'private.pem'
        cls.trust = cls.base / 'trust.py'
        release.keygen(cls.private, cls.trust)
        cls.key = release.load_key(cls.trust)
        cls.src = cls.base / 'src'; cls.src.mkdir()
        (cls.src / 'app_main.py').write_text('def selftest(ctx): return True\ndef run(ctx): pass\n')
        for version in (1, 2, 3):
            release.build(cls.src, cls.base / ('v%d' % version), version,
                          cls.private, cls.trust, '1.25.0')
        cls.tree = cls.base / 'remote'
        release.publish(cls.base / 'v2', cls.tree, cls.trust)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.slots = self.root / 'slots'; self.slots.mkdir()
        shutil.copytree(self.base / 'v1', self.slots / 'A')
        (self.slots / 'B').mkdir()
        self.store = Store(str(self.root / 'state'))
        self.store.save(initial_state(1))
    def tearDown(self): self.tmp.cleanup()
    def updater(self, transport=None):
        return Updater(self.store, transport or Transport(self.tree), self.key,
                       (1, 25, 0), str(self.slots))
    def test_signature_openssl_crosscheck(self):
        raw = (self.base / 'v2/manifest.json').read_bytes()
        sig = (self.base / 'v2/manifest.sig').read_bytes()
        verify_signature(raw, sig, self.key)
        public = self.root / 'public.pem'
        public.write_bytes(release.openssl('pkey', '-in', self.private, '-pubout'))
        binary = self.root / 'signature'; binary.write_bytes(bytes.fromhex(sig.decode()))
        self.assertIn(b'Verified OK', release.openssl('dgst', '-sha256', '-verify', public,
                      '-signature', binary, self.base / 'v2/manifest.json'))
        for bad_raw, bad_sig in ((raw+b' ', sig), (raw, b'0'*512), (raw, sig[:-2]), (raw, b'f'*512)):
            with self.assertRaises(ValueError): verify_signature(bad_raw, bad_sig, self.key)
    def test_path_traversal_reserved(self):
        for path in ('../secret.py', '/app.py', 'a//b.py', 'ota/x.py', 'config.py', 'a\\b.py', 'a.txt'):
            with self.assertRaises(ValueError): valid_path(path)
    def test_signed_schema_and_runtime_rejected(self):
        raw = (self.base / 'v2/manifest.json').read_bytes()
        sig = (self.base / 'v2/manifest.sig').read_bytes()
        with self.assertRaises(ValueError): manifest(raw, sig, self.key, runtime=(1, 23, 0))
        for mutate in (lambda m: m.update(board='OTHER'), lambda m: m.update(version=True),
                       lambda m: m['files'].append(m['files'][0]),
                       lambda m: m['files'][0].update(size=999999)):
            m = json.loads(raw); mutate(m)
            data = json.dumps(m).encode(); p=self.root/'m'; p.write_bytes(data)
            signature=release.openssl('dgst','-sha256','-sign',self.private,p).hex().encode()
            with self.assertRaises(ValueError): manifest(data, signature, self.key)
    def test_install_then_trial_then_rollback(self):
        self.assertTrue(self.updater().install())
        s, slot, trial = choose(self.store)
        self.assertEqual((slot, trial), ('B', True))
        self.assertTrue(s['attempted'])
        s, slot, trial = choose(self.store)
        self.assertEqual((slot, trial, s['floor']), ('A', False, 2))
        self.assertFalse(self.updater().install())  # no replay of failed release
    def test_pending_blocks_install(self):
        self.updater().install()
        with self.assertRaises(ValueError): self.updater().install()
    def test_interrupted_download_preserves_active(self):
        before = self.store.load()
        with self.assertRaises(OSError): self.updater(Transport(self.tree, True)).install()
        self.assertEqual(self.store.load(), before)
        verify_slot(str(self.slots/'A'), self.key, (1,25,0))
    def test_file_tampering_rejected(self):
        self.updater().install()
        p = self.slots/'B/app_main.py'; p.write_text('print("tampered")')
        with self.assertRaises(ValueError): verify_slot(str(self.slots/'B'),self.key,(1,25,0))
    def test_extra_file_rejected(self):
        (self.slots/'A/evil.py').write_text('pass')
        with self.assertRaises(ValueError): verify_slot(str(self.slots/'A'), self.key,(1,25,0))
    def test_torn_state_write_uses_old_record(self):
        s=self.store.load(); s['floor']=2; self.store.save(s)
        latest = self.store.load()
        (self.root / ('state/state%d.json' % (latest['seq']%2))).write_text('{torn')
        self.assertEqual(self.store.load()['floor'], 1)
    def test_both_state_records_invalid_fail_closed(self):
        for i in (0,1): (self.root/('state/state%d.json'%i)).write_text('{}')
        with self.assertRaises(ValueError): self.store.load()
    def test_no_space(self):
        with patch('ota.updater.os.statvfs', return_value=(4096,4096,1,0)):
            with self.assertRaises(OSError): self.updater().install()
        self.assertIsNone(self.store.load()['pending'])
    def test_syntax_error_release_rejected(self):
        source=self.root/'bad';source.mkdir();(source/'app_main.py').write_text('def broken(:')
        with self.assertRaises(SyntaxError):
            release.build(source,self.root/'bad-release',4,self.private,self.trust,'1.25.0')
    def test_http_rejects_bad_framing(self):
        self.assertEqual(headers(io.BytesIO(b'HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\n'),10),3)
        for response in (b'HTTP/1.1 302 Found\r\n\r\n',
                         b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n',
                         b'HTTP/1.1 200 OK\r\nContent-Length: 99\r\n\r\n',
                         b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 2\r\n\r\n',
                         b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\nContent-Length: 2\r\n\r\n'):
            with self.assertRaises((ValueError,OSError)): headers(io.BytesIO(response),10)
    def test_confirm_and_reuse_old_slot(self):
        # Import supervisor with hardware stubs; test actual Context.confirm.
        from types import SimpleNamespace
        fake_time=SimpleNamespace(ticks_ms=lambda:20000,ticks_diff=lambda a,b:a-b)
        fake_config=SimpleNamespace(CONFIRM_AFTER_MS=10000,TRIAL_TIMEOUT_MS=60000)
        with patch.dict(sys.modules,{'machine':SimpleNamespace(), 'config':fake_config}):
            import ota.boot as boot
        self.updater().install(); s,slot,trial=choose(self.store)
        with patch.object(boot,'time',fake_time), patch.object(boot,'config',fake_config):
            ctx=boot.Context(self.store,s,slot,trial,SimpleNamespace(feed=lambda:None))
            ctx.started=0;ctx.confirm()
        s=self.store.load();self.assertEqual((s['active'],s['previous'],s['pending']),('B','A',None))
        remote=self.root/'remote3';release.publish(self.base/'v3',remote,self.trust)
        self.assertTrue(self.updater(Transport(remote)).install())
        self.assertIsNone(self.store.load()['previous'])
        verify_slot(str(self.slots/'B'),self.key,(1,25,0))
    def test_bootstrap_image(self):
        secret=self.root/'secret.py';secret.write_text("WIFI_SSID='test'\nWIFI_PASSWORD='test'\n")
        out=self.root/'image'
        release.provision(self.base/'v1',out,self.trust,secret,ROOT/'device/config.py')
        self.assertEqual(Store(str(out/'ota-state')).load()['active'],'A')
        verify_slot(str(out/'slots/A'),self.key,(1,25,0))


    def test_tampered_payload_never_pending(self):
        remote = self.root/'remote';shutil.copytree(self.tree,remote)
        raw=(remote/'channel/manifest.json').read_bytes()
        path=remote/'releases'/digest(raw)/'app_main.py'
        data=path.read_bytes();path.write_bytes(b'#'+data[1:])
        with self.assertRaises(ValueError): self.updater(Transport(remote)).install()
        self.assertIsNone(self.store.load()['pending'])
        verify_slot(str(self.slots/'A'),self.key,(1,25,0))
    def test_bad_channel_signature_never_touches_slot(self):
        remote=self.root/'remote';shutil.copytree(self.tree,remote)
        (remote/'channel/manifest.sig').write_bytes(b'0'*512)
        with self.assertRaises(ValueError): self.updater(Transport(remote)).install()
        self.assertEqual(list((self.slots/'B').iterdir()),[])
    def test_post_download_syntax_check_prevents_staging(self):
        # A legitimately signed but MicroPython-incompatible source is rejected
        # by the actual target compiler; simulate that compiler's rejection.
        with patch('ota.integrity.compile',side_effect=SyntaxError('target syntax'),create=True):
            with self.assertRaises(SyntaxError): self.updater().install()
        self.assertIsNone(self.store.load()['pending'])
    def test_state_write_failure_does_not_start_candidate(self):
        self.updater().install()
        with patch.object(self.store,'save',side_effect=OSError('flash write fault')):
            with self.assertRaises(OSError): choose(self.store)
        self.assertFalse(self.store.load()['attempted'])
    def test_premature_confirm_rejected(self):
        from types import SimpleNamespace
        with patch.dict(sys.modules,{'machine':SimpleNamespace(),'config':SimpleNamespace()}):
            import ota.boot as boot
        self.updater().install();s,slot,trial=choose(self.store)
        timer=SimpleNamespace(ticks_ms=lambda:100,ticks_diff=lambda a,b:a-b)
        cfg=SimpleNamespace(CONFIRM_AFTER_MS=10000)
        with patch.object(boot,'time',timer),patch.object(boot,'config',cfg):
            ctx=boot.Context(self.store,s,slot,trial,SimpleNamespace())
            with self.assertRaises(ValueError):ctx.confirm()
        self.assertEqual(self.store.load()['active'],'A')
    def test_trial_feed_deadline_resets(self):
        from types import SimpleNamespace
        with patch.dict(sys.modules,{'machine':SimpleNamespace(),'config':SimpleNamespace()}):
            import ota.boot as boot
        class Reset(BaseException): pass
        def reset():raise Reset()
        timer=SimpleNamespace(ticks_ms=lambda:70000,ticks_diff=lambda a,b:a-b)
        cfg=SimpleNamespace(TRIAL_TIMEOUT_MS=60000)
        with patch.object(boot,'time',timer),patch.object(boot,'config',cfg),patch.object(boot,'machine',SimpleNamespace(reset=reset)):
            ctx=boot.Context(self.store,self.store.load(),'B',True,SimpleNamespace(feed=lambda:None))
            ctx.started=0
            with self.assertRaises(Reset):ctx.feed()
    def test_actual_boot_failed_selftest_rolls_back(self):
        from types import SimpleNamespace
        with patch.dict(sys.modules,{'machine':SimpleNamespace(),'config':SimpleNamespace()}):
            import ota.boot as boot
        class Reset(BaseException):pass
        def reset():raise Reset()
        class Pin:
            IN=0;PULL_UP=1
            def __init__(self,*args):pass
            def value(self):return 1
        hardware=SimpleNamespace(Pin=Pin,WDT=lambda **kwargs:SimpleNamespace(feed=lambda:None),reset=reset)
        cfg=SimpleNamespace(RECOVERY_PIN=15,WDT_TIMEOUT_MS=8000)
        timer=SimpleNamespace(ticks_ms=lambda:0)
        fake_app=SimpleNamespace(selftest=lambda ctx:False,run=lambda ctx:self.fail('run after failed selftest'))
        self.updater().install()
        original_path=list(sys.path)
        try:
            with patch.object(boot,'Store',return_value=self.store),patch.object(boot,'verify_slot',return_value={}),patch.object(boot,'machine',hardware),patch.object(boot,'config',cfg),patch.object(boot,'time',timer),patch.dict(sys.modules,{'trust':SimpleNamespace(PUBLIC_KEY=self.key),'app_main':fake_app}):
                with self.assertRaises(Reset):boot.start()
        finally:sys.path[:]=original_path
        self.assertTrue(self.store.load()['attempted'])
        s,slot,trial=choose(self.store)
        self.assertEqual((slot,trial),('A',False))
    def test_successful_trial_survives_next_boot(self):
        self.updater().install();s,slot,trial=choose(self.store)
        s['active'],s['previous'],s['pending'],s['attempted']='B','A',None,False
        self.store.save(s)
        s,slot,trial=choose(self.store)
        self.assertEqual((slot,trial),('B',False))
    def test_keygen_refuses_overwrite(self):
        before=self.private.read_bytes()
        with self.assertRaises(ValueError):release.keygen(self.private,self.trust)
        self.assertEqual(self.private.read_bytes(),before)

if __name__ == '__main__': unittest.main()
