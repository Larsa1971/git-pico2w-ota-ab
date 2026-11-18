# Testprotokoll och ärlig verifieringsnivå

Hosttester kör den verkliga signatur-, manifest-, lagrings- och uppdateringskoden under CPython, med filsystem/transport på datorn. De ersätter inte MicroPython på RP2350. De medföljande leveransresultaten finns i TEST_RESULTS.md.

## Innan en produktionsrelease

Notera kortrevision, firmware-UF2-version/hash, `sys.implementation`, `os.uname()`, ledig flash/RAM, WDT- och tidsinställningar. Kör följande på ett separat testkort med USB-loggning.

| Prov | Godkänt resultat |
|---|---|
| `device_probe.py` i GP15-serviceläge | Bigint/signatur, samtliga slot-A-hashar och MicroPython-kompilering fungerar, självtest True |
| Kallstart av provisionerad A | LED/produktapp kör och nätverksfel hindrar inte lokalfunktionen |
| Giltig version 2 | B staged, trial, självtest och explicit commit; A blir previous |
| Version 3 som kastar i selftest | Automatisk reset och B återgår som aktiv; version 3 provas inte igen |
| Version 4 med oändlig loop i selftest, utan feed | Hårdvaru-WDT reset; gammal active startar |
| Kandidat som feedar utan confirm | Context återställer efter TRIAL_TIMEOUT_MS; rollback |
| Modifierad fil/signatur | Avvisas före aktivering |
| Giltigt signerat fel board/runtime/path | Avvisas före slotbyte |
| Avbrutet Wi-Fi/TLS/ström under payload | Aktiv slot kör efter återstart |
| Strömavbrott under pending/attempted/confirm | Resultat enligt ARCHITECTURE.md; upprepa många gånger |
| Otillräcklig flash / MemoryError | Ingen ofullständig kandidat aktiveras |
| Fel TLS-handshake, chunked/redirect | Nätuppdatering avvisas, ingen osäker fallback |
| Båda statusposter trasiga | USB-serviceläge/recovery; ingen osignerad auto-vald app |
| GP15 till GND vid hård reset | App och WDT startar inte; USB går att använda |
| Långtidstest minst 24 h | Ingen oönskad reset; mät högsta tider för DNS, TLS, RSA, compile och självtest |

För rollback-prov: bygg en avsiktligt trasig men **signerad** testapp med ett nytt versionsnummer. Återställ inte `floor` för att återprova, skapa en ny högre testversion. Ha inga farliga laster anslutna under dessa tester.

## Kompilering och självtest

Hostens `compile()` fångar CPython-syntaxfel. Valfri `--mpy-cross` ger ytterligare MicroPython-syntaxkontroll, men hosten kör inte appar mot RP2350-drivrutiner. Enheten kompilerar varje fil igen före staging och före import. Den verkliga appens självtest körs bara på enheten, före commit. Exempelappens LED-test är avsiktligt litet och måste utökas för din hårdvara.

Under GP15-serviceläge: `mpremote connect auto run tools/device_probe.py`. Detta importerar och kör aktiva appens selftest, med samma privilegier som appen. Kör enbart på avsedd signerad kod och säker testhårdvara. Sätt inga GP15-laster som gör servicebygeln farlig.
