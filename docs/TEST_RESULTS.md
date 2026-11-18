# Leveranskontroll 2026-11-06

Miljö: macOS, CPython 3.12.2, OpenSSL 3.2.0. Ingen fysisk Pico ansluten; ingen lokal MicroPython-tolk eller mpy-cross tillgänglig.

- `sh tools/precommit.sh`: **24 tester godkända**.
- `compileall` av device, app, tools och tests: godkänd under CPython.
- RSA-verifieraren korsverifierad mot OpenSSL med temporär RSA-2048-nyckel.
- Testat: manifest-/signaturfel, filhashar, oväntade filer, osäkra paths, board/runtime, storleksgränser, versionsspärr, avbruten nedladdning, för lite lagring, fel i kompilering, trasiga statusposter, status-skrivfel, provstart/rollback, faktiskt supervisorflöde med misslyckat självtest, för tidig confirm, provtidsgräns, lyckad commit och återanvändning av gammal slot samt provisionering.
- HTTP-parser testad mot giltig framing och avvisning av redirect, chunked, gzip, för stor body och dubbla headers.
- ZIP kontrollerad med CRC och innehållslista; inga privata nycklar, Wi-Fi-hemligheter, cachefiler eller Git-internals inkluderas.

Ej verifierat: fysisk RP2350, verklig MicroPython-kompilering/RAM, MicroPython-bigint/RSA-tid, TLS-anslutning till GitHub och HTTP-framing från enheten, Wi-Fi, watchdog i hårdvara eller strömavbrott på flash. Följ HARDWARE.md innan drift. Testresultatet innebär inte att produkten är produktionskvalificerad.

Officiella underlag som kontrollerades: [Pico 2 W-firmware](https://micropython.org/download/RPI_PICO2_W/), [TLS](https://docs.micropython.org/en/latest/library/ssl.html), [watchdog](https://docs.micropython.org/en/latest/library/machine.WDT.html), [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html). Pico 2 W:s första listade stabila version är 1.25.0, som används som minimum här. Dokumentationen för latest kan avvika från din valda stabila firmware.
