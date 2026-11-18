import os
from ota.integrity import manifest, verify_slot, MAX_MANIFEST, digest
from ota.storage import mkdir, parents, remove_tree, sync

class Updater:
    def __init__(self, store, transport, key, runtime, root='/slots', feed=lambda: None):
        self.store, self.transport, self.key = store, transport, key
        self.runtime, self.root, self.feed = runtime, root, feed

    def install(self):
        s = self.store.load()
        if s['pending']:
            raise ValueError('trial pending; OTA forbidden')
        raw = self.transport.get('channel/manifest.json', MAX_MANIFEST)
        sig = self.transport.get('channel/manifest.sig', 512)
        m = manifest(raw, sig, self.key, runtime=self.runtime)
        if m['version'] <= s['floor']:
            return False
        # Signed manifest digest binds all payload paths to an immutable release.
        release = 'releases/' + digest(raw) + '/'
        slot = 'B' if s['active'] == 'A' else 'A'
        target = self.root + '/' + slot
        total = sum(f['size'] for f in m['files'])
        stat = os.statvfs(self.root)
        if stat[0] * stat[3] < total + 32768:
            raise OSError('insufficient free flash (conservative check)')
        # Retire fallback reference BEFORE reusing it, retaining current active.
        if s['previous'] == slot:
            s['previous'] = None
            s = self.store.save(s)
        remove_tree(target)
        mkdir(target)
        for f in m['files']:
            path = target + '/' + f['path']
            parents(path)
            with open(path, 'wb') as output:
                self.transport.fetch(release + f['path'], f['size'], output.write)
                output.flush()
            self.feed()
        for name, data in (('manifest.json', raw), ('manifest.sig', sig)):
            with open(target + '/' + name, 'wb') as out:
                out.write(data)
                out.flush()
        sync()
        verify_slot(target, self.key, self.runtime, self.feed)
        # Only now make the candidate bootable. Runtime selftest runs after reset.
        s['pending'], s['attempted'], s['floor'] = slot, False, m['version']
        self.store.save(s)
        return True
