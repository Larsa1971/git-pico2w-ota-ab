"""Two alternating state records. A torn new write leaves previous record intact."""
import os
import json
from ota.integrity import digest, read_limited

def sync():
    if hasattr(os, 'sync'):
        os.sync()

def mkdir(path):
    try:
        os.mkdir(path)
    except OSError:
        if not os.stat(path)[0] & 0x4000:
            raise

def parents(path):
    bits = path.split('/')
    for i in range(1, len(bits)):
        p = '/'.join(bits[:i])
        if p:
            mkdir(p)

def remove_tree(path):
    try:
        names = os.listdir(path)
    except OSError:
        return
    for name in names:
        p = path + '/' + name
        if os.stat(p)[0] & 0x4000:
            remove_tree(p)
        else:
            os.remove(p)
    os.rmdir(path)

def validate(s):
    if set(s) != {'seq', 'active', 'previous', 'pending', 'attempted', 'floor'}:
        raise ValueError('state fields')
    if type(s['seq']) is not int or s['seq'] < 0 or type(s['floor']) is not int or s['floor'] < 1:
        raise ValueError('state counters')
    if s['active'] not in ('A', 'B') or s['previous'] not in (None, 'A', 'B'):
        raise ValueError('state slots')
    if s['pending'] not in (None, 'A', 'B') or type(s['attempted']) is not bool:
        raise ValueError('state pending')
    if s['pending'] == s['active'] or (s['attempted'] and not s['pending']):
        raise ValueError('state transition')
    return s

class Store:
    def __init__(self, root='/ota-state'):
        self.root = root
        mkdir(root)

    def load(self):
        records = []
        for i in (0, 1):
            try:
                env = json.loads(read_limited(self.root + '/state%d.json' % i, 2048))
                raw = env['payload']
                if digest(raw.encode()) != env['sha256']:
                    continue
                records.append(validate(json.loads(raw)))
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if not records:
            raise ValueError('no valid state; USB recovery required')
        return max(records, key=lambda s: s['seq'])

    def save(self, state):
        s = dict(state)
        s['seq'] += 1
        validate(s)
        raw = json.dumps(s)
        path = self.root + '/state%d.json' % (s['seq'] % 2)
        with open(path, 'w') as f:
            f.write(json.dumps({'payload': raw, 'sha256': digest(raw.encode())}))
            f.flush()
        sync()
        # Read-back catches ordinary storage faults before proceeding.
        if self.load() != s:
            raise OSError('state read-back failed')
        return s

def initial_state(version):
    return {'seq': 0, 'active': 'A', 'previous': None, 'pending': None,
            'attempted': False, 'floor': version}

def choose(store):
    s = store.load()
    if s['pending'] and s['attempted']:
        s['pending'], s['attempted'] = None, False
        s = store.save(s)
    if s['pending']:
        s['attempted'] = True
        s = store.save(s)  # Persist BEFORE executing any candidate code.
        return s, s['pending'], True
    return s, s['active'], False
