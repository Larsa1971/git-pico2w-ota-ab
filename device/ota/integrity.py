"""Small strict RSA-2048 PKCS#1 v1.5/SHA-256 verifier; no private key on board."""
import hashlib
import binascii
import json
import os

MAX_MANIFEST = 12288
MAX_FILES = 32
MAX_FILE = 65536
MAX_TOTAL = 262144
PREFIX = binascii.unhexlify('3031300d060960864801650304020105000420')
RESERVED = ('ota', 'config', 'secret', 'machine', 'network', 'ssl', 'socket',
            'os', 'sys', 'time', 'hashlib', 'binascii', 'json', 'gc', 'ntptime')

def digest(data):
    return binascii.hexlify(hashlib.sha256(data).digest()).decode()

def verify_signature(raw, signature, key):
    if len(raw) > MAX_MANIFEST or len(signature) != 512:
        raise ValueError('signature/manifest size')
    sig = binascii.unhexlify(signature)
    n = int(key['n'], 16)
    if len(key['n']) != 512 or n >> 2047 != 1 or key['e'] != 65537:
        raise ValueError('RSA-2048 / e=65537 required')
    x = int(binascii.hexlify(sig), 16)
    if x >= n:
        raise ValueError('signature range')
    # Portable modular exponentiation; only 17 squarings for public e.
    result, base, exponent = 1, x, 65537
    while exponent:
        if exponent & 1:
            result = (result * base) % n
        base = (base * base) % n
        exponent >>= 1
    encoded = binascii.unhexlify(('%0512x' % result))
    tail = PREFIX + hashlib.sha256(raw).digest()
    expected = b'\x00\x01' + b'\xff' * (256 - len(tail) - 3) + b'\x00' + tail
    if encoded != expected:
        raise ValueError('invalid manifest signature')

def valid_path(path):
    if not isinstance(path, str) or len(path) > 100:
        raise ValueError('path type/length')
    parts = path.split('/')
    for part in parts:
        if not part or part in ('.', '..') or not all(c in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.' for c in part):
            raise ValueError('unsafe path')
    if parts[0].split('.')[0] in RESERVED or path in ('manifest.json', 'manifest.sig'):
        raise ValueError('reserved path')
    if not path.endswith('.py'):
        raise ValueError('only Python source supported')
    return path

def manifest(raw, signature, key, board='RPI_PICO2_W', runtime=(1, 25, 0)):
    verify_signature(raw, signature, key)  # Authenticate bytes BEFORE parsing.
    m = json.loads(raw)
    if set(m) != {'schema', 'board', 'version', 'min_micropython', 'files'}:
        raise ValueError('manifest fields')
    if m['schema'] != 1 or m['board'] != board:
        raise ValueError('schema/board')
    if type(m['version']) is not int or not 0 < m['version'] < 2147483647:
        raise ValueError('version must be positive integer')
    v = m['min_micropython']
    if not isinstance(v, list) or len(v) != 3 or any(type(x) is not int or x < 0 for x in v):
        raise ValueError('runtime version')
    if tuple(runtime[:3]) < tuple(v):
        raise ValueError('MicroPython too old')
    files = m['files']
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError('file count')
    names, total = [], 0
    for f in files:
        if set(f) != {'path', 'size', 'sha256'}:
            raise ValueError('file fields')
        p = valid_path(f['path'])
        if p in names:
            raise ValueError('duplicate path')
        names.append(p)
        if type(f['size']) is not int or not 0 < f['size'] <= MAX_FILE:
            raise ValueError('file size')
        h = f['sha256']
        if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
            raise ValueError('hash')
        total += f['size']
    if total > MAX_TOTAL or 'app_main.py' not in names:
        raise ValueError('total size/entry point')
    return m

def read_limited(path, maximum):
    with open(path, 'rb') as f:
        data = f.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError('oversize file')
    return data

def walk(root, prefix=''):
    result = []
    for name in os.listdir(root):
        p = root + '/' + name
        rel = prefix + name
        if os.stat(p)[0] & 0x4000:
            result.extend(walk(p, rel + '/'))
        else:
            result.append(rel)
    return result

def verify_slot(root, key, runtime, feed=lambda: None):
    raw = read_limited(root + '/manifest.json', MAX_MANIFEST)
    sig = read_limited(root + '/manifest.sig', 512)
    m = manifest(raw, sig, key, runtime=runtime)
    expected = [f['path'] for f in m['files']] + ['manifest.json', 'manifest.sig']
    if sorted(walk(root)) != sorted(expected):
        raise ValueError('unexpected or missing files')
    for f in m['files']:
        data = read_limited(root + '/' + f['path'], f['size'])
        if len(data) != f['size'] or digest(data) != f['sha256']:
            raise ValueError('file integrity: ' + f['path'])
        code = compile(data.decode('utf-8'), f['path'], 'exec')
        del code, data
        feed()
    return m
