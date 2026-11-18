# Keep this trusted root outside application slots.
try:
    from ota.boot import start
    start()
except Exception as exc:
    print('OTA supervisor unavailable; use USB recovery:', repr(exc))
