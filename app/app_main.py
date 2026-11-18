import time
import machine

# Contract: no side effects at import. selftest returns bool; run never returns.
def selftest(ctx):
    led = machine.Pin('LED', machine.Pin.OUT)
    led.off()
    ctx.feed()
    return True

def connect(ctx):
    import network
    import secret
    import config
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(secret.WIFI_SSID, secret.WIFI_PASSWORD)
    began = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), began) > config.WIFI_TIMEOUT_MS:
            raise OSError('Wi-Fi timeout')
        ctx.feed()
        time.sleep_ms(100)
    return wlan

def run(ctx):
    import config
    led = machine.Pin('LED', machine.Pin.OUT)
    began = time.ticks_ms()
    next_ota = began
    while True:
        led.toggle()
        # Replace with meaningful sensor/peripheral health checks.
        ctx.feed()
        if ctx.trial and time.ticks_diff(time.ticks_ms(), began) >= config.CONFIRM_AFTER_MS:
            ctx.confirm()
        if not ctx.trial and time.ticks_diff(time.ticks_ms(), next_ota) >= 0:
            next_ota = time.ticks_add(time.ticks_ms(), config.OTA_INTERVAL_MS)
            try:
                connect(ctx)
                ctx.check_update()
            except Exception as exc:
                print('OTA deferred:', repr(exc))
        time.sleep_ms(500)
