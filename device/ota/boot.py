import sys
import time
import machine
import config
from ota.storage import Store, choose
from ota.integrity import verify_slot

class Context:
    def __init__(self, store, state, slot, trial, wdt):
        self.store, self.state, self.slot = store, state, slot
        self.trial, self.wdt = trial, wdt
        self.started = time.ticks_ms()

    def feed(self):
        # Candidate cannot indefinitely postpone confirmation using this API.
        if self.trial and time.ticks_diff(time.ticks_ms(), self.started) > config.TRIAL_TIMEOUT_MS:
            machine.reset()
        self.wdt.feed()

    def confirm(self):
        if not self.trial:
            return
        if time.ticks_diff(time.ticks_ms(), self.started) < config.CONFIRM_AFTER_MS:
            raise ValueError('health observation period not complete')
        s = self.store.load()
        if s['pending'] != self.slot or not s['attempted']:
            raise ValueError('trial state changed')
        s['previous'], s['active'] = s['active'], self.slot
        s['pending'], s['attempted'] = None, False
        self.state = self.store.save(s)
        self.trial = False
        print('OTA confirmed:', self.slot)

    def check_update(self):
        if self.trial:
            return False
        from ota.http import GitHub
        from ota.updater import Updater
        import trust
        updater = Updater(self.store, GitHub(config, self.feed), trust.PUBLIC_KEY,
                          sys.implementation.version, feed=self.feed)
        if updater.install():
            machine.reset()
        return False

def start():
    import trust
    # Recovery jumper GP15 to GND bypasses app/WDT; leave it out in production.
    pin = machine.Pin(config.RECOVERY_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
    if not pin.value():
        print('USB recovery mode; application disabled')
        return
    store = Store()
    s, slot, trial = choose(store)
    wdt = machine.WDT(timeout=config.WDT_TIMEOUT_MS)
    ctx = Context(store, s, slot, trial, wdt)
    try:
        verify_slot('/slots/' + slot, trust.PUBLIC_KEY, sys.implementation.version, ctx.feed)
        sys.path.insert(0, '/slots/' + slot)
        import app_main
        if app_main.selftest(ctx) is not True:
            raise ValueError('application selftest failed')
        app_main.run(ctx)
        raise RuntimeError('application returned unexpectedly')
    except Exception as exc:
        print('Boot/app failed:', repr(exc))
        # Trial is rolled back by choose() on next hard reset.
        # A confirmed app failure can use retained previous signed slot once.
        if not trial and s['previous']:
            old = s['active']
            s['active'], s['previous'] = s['previous'], None
            store.save(s)
            print('Fallback from', old, 'to', s['active'])
        machine.reset()
