# Arkitektur och avbrottspunkter

MicroPython kör rotens `boot.py` och `main.py`. Supervisorn kontrollerar servicebygel, läser status, markerar provförsök och verifierar vald slot före import. `sys.path` pekas till vald slot. Appen körs med fulla MicroPython-rättigheter; detta är ingen sandbox.

```text
/boot.py, /main.py, /ota/        betrodd, USB-underhållen supervisor
/config.py, /secret.py          lokala inställningar
/trust.py                       publik signeringsnyckel
/ota-state/state0.json           alternerande status + SHA-256
/ota-state/state1.json
/slots/A/manifest.json + .sig + appfiler
/slots/B/manifest.json + .sig + appfiler
```

## Tillstånd

`active` är bekräftad slot. `pending` är färdig kandidat. `attempted` skrivs beständigt före kandidatimport. `previous` är föregående bekräftad slot, om den ännu finns kvar. `floor` är högsta staged versionsnummer; `seq` avgör senaste giltiga statusposten.

1. Hämta begränsat manifest och detached signatur, verifiera RSA före JSON-tolkning.
2. Validera schema, board, runtime, paths, storlekar och monotont versionsnummer.
3. Kontrollera ledigt utrymme konservativt (före radering; kan neka trots att utrymme skulle frigöras).
4. Pensionera eventuell `previous`-referens till mål-slotten. Radera endast inaktiv slot och skriv om från början.
5. Hämta signerade filer från digest-katalog, skriv manifest/signatur, flush + sync.
6. Läs tillbaka exakt filuppsättning, hash, storlek och kompilera varje `.py` på enheten.
7. Spara `pending`, `attempted=False`, `floor=version` i den andra statusposten; läs tillbaka. Reset görs av Context.
8. Nästa boot sparar `attempted=True` före import. Självtest följs av hälsoperiod och explicit `ctx.confirm()`.
9. Commit byter `active` och sätter `previous`. Om reset sker före commit rensas i stället pending och gamla active körs.

## Strömavbrott

| Avbrott | Förväntat resultat om filsystemet är intakt |
|---|---|
| Under manifest/nedladdning/kompilering | Aktiv slot startar; partiell inaktiv slot ignoreras |
| Under pending-skrivning | Senaste giltiga status avgör; gammal aktiv eller komplett kandidat |
| Efter attempted, före commit | Rollback till aktiv slot |
| Under commit | Tidigare giltig post ger rollback, ny giltig post ger ny aktiv |
| Båda posterna skadade | Ingen gissning efter högsta appversion; USB-återställning |

Statusposterna skrivs växelvis utan att båda ersätts samtidigt. Checksumman upptäcker oavsiktliga skador men är inte autentisering. Filsystemets durability vid spänningsfall är inget som Python-kod kan garantera; LittleFS och `os.sync()` reducerar risken, men båda posterna ligger på samma flash.

## Begränsningar och budget

Högst 32 filer, 64 KiB/fil, 256 KiB totalt och 12 KiB manifest. Alla filer måste vara UTF-8 `.py`. En fil läses i RAM för kompilering; kompilerad kod kräver ytterligare RAM. Gränserna är tak, ingen RAM-garanti. För stora importer/kompileringar kan ge MemoryError eller WDT-reset, vilket lämnar active orörd under staging eller ger rollback under trial.

Nedladdning streamas i 1024-byteblock. Socket-timeout är 3 s, body-deadline 30 s per fil. DNS/TLS/headers kan ändå blockera och watchdogens 8 s ger yttersta återstart. WDT får bara mat mellan steg/block; om en firmwarefunktion blockerar för länge kan en fungerande uppdatering därför misslyckas. Avsiktligt ingen bakgrundstimer som matar WDT vid låsning. TLS/framing-/nätverksfel fångas av appen och nästa kontroll sker vid nästa intervall; pågående trial gör ingen OTA.

Enhetsverifiering kan inte bevisa att alla kodvägar fungerar, att imports finns eller att hårdvara fungerar. Självtest och observation kompletterar syntaxkontroll. Behov av native-moduler måste provisioneras via firmware/USB.
