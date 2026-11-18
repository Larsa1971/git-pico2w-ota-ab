# Run on target with GP15 grounded, after full provisioning, before removing jumper.
import sys
import os
import gc
import ssl
import trust
from ota.storage import Store
from ota.integrity import verify_slot

print('Runtime:', sys.implementation)
print('Board:', os.uname())
if sys.implementation.name != 'micropython':
    raise RuntimeError('This probe must run on the target, not CPython')
if not hasattr(ssl, 'SSLContext'):
    raise RuntimeError('SSLContext missing')
s = Store().load()
root = '/slots/' + s['active']
m = verify_slot(root, trust.PUBLIC_KEY, sys.implementation.version)
print('Signature, hashes, file set and on-target compile OK:', m['version'])
sys.path.insert(0, root)
import app_main
class ProbeContext:
    trial = True
    def feed(self): pass
    def confirm(self): raise RuntimeError('selftest must not confirm')
    def check_update(self): raise RuntimeError('selftest must not update')
if app_main.selftest(ProbeContext()) is not True:
    raise RuntimeError('selftest failed')
gc.collect()
print('Selftest OK; free RAM:', gc.mem_free())
print('TLS network validation and WDT/power-cut qualification still required.')
