#!/usr/bin/env python3
"""Host tooling. Requires Python 3.10+ and OpenSSL 3.x. No Python crypto dependency."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'device'))
from ota.integrity import manifest, verify_slot, valid_path
from ota.storage import Store, initial_state

def openssl(*args, **kw):
    return subprocess.run(['openssl', *map(str, args)], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw).stdout

def keygen(private, trust):
    private, trust = Path(private), Path(trust)
    if private.exists():
        raise ValueError('refuse to overwrite existing private key')
    private.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation and restrictive permissions even with permissive umask.
    fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        openssl('genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048', '-out', private)
        modulus = openssl('rsa', '-in', private, '-noout', '-modulus').decode().strip().split('=')[1].lower()
        key = {'n': modulus, 'e': 65537}
        trust.parent.mkdir(parents=True, exist_ok=True)
        trust.write_text('# Public verification key; private key remains on signing host.\nPUBLIC_KEY = ' + repr(key) + '\n')
    except BaseException:
        private.unlink(missing_ok=True)
        raise

def load_key(path):
    # Parse generated assignment as literal, never execute trust files on host.
    import ast
    tree = ast.parse(Path(path).read_text())
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        raise ValueError('trust file format')
    return ast.literal_eval(tree.body[0].value)

def build(source, output, version, private, trust, minimum, mpy=None):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('output already exists; use a new directory')
    key = load_key(trust)
    files = []
    for path in sorted(source.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink forbidden')
        if not path.is_file():
            continue
        name = valid_path(path.relative_to(source).as_posix())
        data = path.read_bytes()
        compile(data.decode('utf8'), name, 'exec')
        if mpy:
            # Compiler is explicit: use mpy-cross from the exact firmware release.
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run([mpy, '-o', str(Path(tmp) / 'check.mpy'), str(path)], check=True)
        files.append({'path': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    m = {'schema': 1, 'board': 'RPI_PICO2_W', 'version': version,
         'min_micropython': list(map(int, minimum.split('.'))), 'files': files}
    raw = json.dumps(m, sort_keys=True, separators=(',', ':')).encode()
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / 'manifest.json'
        p.write_bytes(raw)
        sig = openssl('dgst', '-sha256', '-sign', private, p).hex().encode()
    manifest(raw, sig, key, runtime=(999, 0, 0))
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.release-', dir=output.parent))
    try:
        for f in files:
            target = temp / f['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (source / f['path']).read_bytes()
            if hashlib.sha256(data).hexdigest() != f['sha256']:
                raise ValueError('source changed during build')
            target.write_bytes(data)
        (temp / 'manifest.json').write_bytes(raw)
        (temp / 'manifest.sig').write_bytes(sig)
        verify_slot(str(temp), key, (999, 0, 0))
        temp.rename(output)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return hashlib.sha256(raw).hexdigest()

def publish(release, destination, trust):
    release, destination = Path(release), Path(destination)
    verify_slot(str(release), load_key(trust), (999, 0, 0))
    digest = hashlib.sha256((release / 'manifest.json').read_bytes()).hexdigest()
    payload = destination / 'releases' / digest
    if payload.exists():
        # Immutable paths: refuse collisions or changed existing files.
        verify_slot(str(payload), load_key(trust), (999, 0, 0))
        if (payload / 'manifest.json').read_bytes() != (release / 'manifest.json').read_bytes():
            raise ValueError('release collision')
    else:
        payload.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(release, payload)
    channel = destination / 'channel'
    channel.mkdir(parents=True, exist_ok=True)
    for name in ('manifest.json', 'manifest.sig'):
        shutil.copyfile(release / name, channel / name)
    print('Prepared GitHub tree:', destination, 'release:', digest)

def provision(release, output, trust, secret, config):
    release, output = Path(release), Path(output)
    if output.exists():
        raise ValueError('provision output must not exist')
    m = verify_slot(str(release), load_key(trust), (999, 0, 0))
    # Validate mandatory local inputs before creating device image.
    for path in (secret, config):
        if not Path(path).is_file():
            raise ValueError('missing provisioning input: ' + str(path))
    shutil.copytree(ROOT / 'device', output,
                    ignore=shutil.ignore_patterns('__pycache__', '*.example', 'secret.py'))
    for src, name in ((trust, 'trust.py'), (secret, 'secret.py'), (config, 'config.py')):
        shutil.copyfile(src, output / name)
    shutil.copytree(release, output / 'slots' / 'A')
    (output / 'slots' / 'B').mkdir()
    store = Store(str(output / 'ota-state'))
    s = store.save(initial_state(m['version']))
    store.save(s)  # Both records valid for initial provisioning.
    print('USB image prepared:', output, '(contains Wi-Fi secrets; do not publish)')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('keygen')
    p.add_argument('--private', required=True); p.add_argument('--trust', required=True)
    p = sub.add_parser('build')
    p.add_argument('--source', default='app'); p.add_argument('--output', required=True)
    p.add_argument('--version', type=int, required=True); p.add_argument('--private', required=True)
    p.add_argument('--trust', default='device/trust.py'); p.add_argument('--minimum', default='1.25.0')
    p.add_argument('--mpy-cross', dest='mpy')
    p = sub.add_parser('verify')
    p.add_argument('--release', required=True); p.add_argument('--trust', default='device/trust.py')
    p = sub.add_parser('publish-tree')
    p.add_argument('--release', required=True); p.add_argument('--destination', required=True)
    p.add_argument('--trust', default='device/trust.py')
    p = sub.add_parser('provision')
    p.add_argument('--release', required=True); p.add_argument('--output', required=True)
    p.add_argument('--trust', default='device/trust.py'); p.add_argument('--secret', required=True)
    p.add_argument('--config', default='device/config.py')
    a = vars(parser.parse_args()); cmd = a.pop('cmd')
    if cmd == 'keygen': keygen(**a)
    elif cmd == 'build': print('Release SHA-256:', build(**a))
    elif cmd == 'verify': print(verify_slot(a['release'], load_key(a['trust']), (999, 0, 0)))
    elif cmd == 'publish-tree': publish(**a)
    elif cmd == 'provision': provision(**a)

if __name__ == '__main__':
    main()
