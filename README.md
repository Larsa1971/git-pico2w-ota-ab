# Pico 2 W – signerad MicroPython OTA med app-A/B

Komplett startrepo för **Raspberry Pi Pico 2 W (RP2350)**. Appen ligger i två kataloger på ett gemensamt filsystem; uppdateringar hämtas från ett publikt GitHub-repo. Ingen separat OTA-server behövs.

**Detta är app-A/B, inte firmware-A/B eller secure boot.** MicroPython-firmware, filsystem, `boot.py`, `main.py`, `ota/`, `config.py`, `secret.py` och den publika nyckeln delas. De uppdateras via USB. Ett trasigt gemensamt filsystem, skadad supervisor eller firmware kan kräva BOOTSEL/USB-återställning. Den egenimplementerade RSA-verifieraren är testad mot OpenSSL men inte oberoende säkerhetsgranskad. Hårdvarukvalificering återstår; se [testprotokollet](docs/HARDWARE.md).

## Egenskaper

- Signerat manifest: RSA-2048, exponent 65537, PKCS#1 v1.5 och SHA-256. Ingen privat signeringsnyckel på Pico.
- Exakt filuppsättning, storlek och SHA-256 per fil; strikt sökvägs-, plattforms-, runtime- och versionskontroll.
- CPython-kompilering vid release, valfri `mpy-cross` och faktisk `compile()` på enheten före aktivering och vid start.
- Streaming till inaktiv slot, begränsade storlekar, TLS utan CA-certifikatvalidering, inga redirects.
- Två checksummeskyddade statusposter; aktiv slot lämnas orörd under nedladdning.
- En provstart. Självtest + minst 10 s hälsoperiod före bekräftelse. Watchdog och 60 s provtidsgräns.
- Avbruten provstart återgår till aktiv slot. Misslyckad version erbjuds inte igen; publicera ett högre heltalsnummer.
- `secret.py` för Wi-Fi; `config.py` för övrigt. Inga riktiga hemligheter eller signeringsnycklar medföljer.

## Kataloger

```text
device/                 betrodd USB-installerad rot och ota-paket
app/app_main.py          exempelapp som publiceras till en slot
tools/release.py         nycklar, bygge, verifiering, GitHub-träd, USB-image
tools/device_probe.py    manuell kontroll på verklig MicroPython
tools/precommit.sh       hosttester och syntaxkontroll
tests/                  nätverks-, integritets- och tillståndstester
docs/                   arkitektur, säkerhet, hårdvaruprov och felsökning
.github/workflows/      tester vid push/PR
```

## 1. Förbered Mac / VS Code

Öppna repot i VS Code. Python 3.10+ och OpenSSL 3.x behövs på datorn. På macOS kan `openssl` vara LibreSSL; välj en OpenSSL 3-installation i PATH. Verktyget använder inga externa Python-kryptobibliotek.

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
openssl version
sh tools/precommit.sh
```

Ladda ned en **stabil MicroPython för RPI_PICO2_W**, minst 1.25.0, från [officiella boardsidan](https://micropython.org/download/RPI_PICO2_W/). Välj exakt firmwareversion för produktionen och använd samma version av `mpy-cross`. Versionen som anges här är en nedre programgräns, inte ett intyg om att alla senare firmwarebyggen fungerar.

Håll BOOTSEL vid USB-anslutning och kopiera rätt UF2 till enheten som visas. Använd en USB-kabel med data. I VS Code-terminalen:

```sh
ls /dev/cu.usbmodem*
mpremote connect auto exec "import sys, os; print(sys.implementation); print(os.uname())"
```

Stäng andra seriella anslutningar innan `mpremote` används. VS Code används som editor; inga tillägg krävs.

## 2. Skapa egen signeringsnyckel och första release

```sh
python3 tools/release.py keygen --private keys/release.pem --trust device/trust.py
python3 tools/release.py build --source app --output build/v1 --version 1 --private keys/release.pem
python3 tools/release.py verify --release build/v1
```

Säkerhetskopiera den privata nyckeln krypterat/offline. `keys/` ignoreras av Git. `device/trust.py` innehåller enbart publik nyckel och ska versionshanteras. RSA används för portabilitet utan en extra Ed25519-modul; se [säkerhetsmodellen](docs/SECURITY.md).

För ytterligare kompilering med **exakt matchande** MicroPython-kompilator:

```sh
python3 tools/release.py build --source app --output build/v1-checked --version 1 --private keys/release.pem --mpy-cross /absolute/path/to/mpy-cross
```

Resultatet innehåller fortfarande `.py`, inte `.mpy`. `.mpy`-ABI och arkitekturspecifik native-kod ingår inte i detta protokoll.

## 3. Wi-Fi, GitHub och TLS (utan CA-verifiering)

Kopiera `device/secret.py.example` till `device/secret.py` och fyll i ditt 2,4 GHz-nätverk. Ändra `device/config.py`:

```python
GITHUB_OWNER = 'ditt-konto'
GITHUB_REPO = 'ditt-repo'
GITHUB_REF = 'ota'
```

Använd ett **publikt repo** och en separat branch med enkelt namn, t.ex. `ota`. Tokens/private repos stöds inte. HTTPS används men **servercertifikatet verifieras inte** och någon `github-ca.pem` behövs inte. Detta gör att en angripare på nätverket kan utge sig för att vara GitHub, se eller ändra OTA-trafik och blockera uppdateringar. Installationen skyddas i stället av obligatorisk RSA-signatur på manifestets exakta bytes och SHA-256 för varje fil. Ingen osignerad kod får installeras. Antirollback via `floor` är best effort och skyddar inte mot manipulation av enhetens flash.

**Viktigt:** detta är ett avsiktligt säkerhetsavsteg, inte samma säkerhetsnivå som verifierad HTTPS. Testa TLS-API och signaturkontroller på din faktiska MicroPython-version.

## 4. Förbered och installera första USB-imagen

```sh
python3 tools/release.py provision --release build/v1 --output build/usb-v1 --secret device/secret.py
```

Imagen innehåller den signerade appen i A, tom B och initialiserad status. Den innehåller också Wi-Fi-lösenord och ska **aldrig publiceras**. Ändra inte appfilerna i imagen: då slutar signaturen/hasharna att stämma.

**På en tom eller avsiktligt återställd enhet:** koppla GP15 till GND som servicebygel och installera filerna. Kör kommandona från reporoten, ett i taget:

```sh
mpremote connect auto fs cp -r build/usb-v1/ota/ :ota/
mpremote connect auto fs cp -r build/usb-v1/slots/ :slots/
mpremote connect auto fs cp -r build/usb-v1/ota-state/ :ota-state/
mpremote connect auto fs cp build/usb-v1/config.py :config.py
mpremote connect auto fs cp build/usb-v1/secret.py :secret.py
mpremote connect auto fs cp build/usb-v1/trust.py :trust.py
mpremote connect auto fs cp build/usb-v1/boot.py :boot.py
mpremote connect auto fs cp build/usb-v1/main.py :main.py
mpremote connect auto rtc --set
mpremote connect auto run tools/device_probe.py
```

`main.py` installeras sist. Avbryt vid första fel; ta inte bort servicebygeln förrän alla steg lyckats. Använd inte detta kopieringsflöde för vanlig OTA eller för att skriva över en enhet som kör appen. Ta bort GP15-bygeln och gör en fysisk omstart. Första appen är lokalt provisionerad och redan betrodd som aktiv; OTA-versioner måste däremot klara en provstart.

## 5. Publicera OTA på GitHub

Skapa en lokal checkout av din dedikerade `ota`-branch (utan privata filer). `publish-tree` skapar bara filer lokalt, inga nätverksändringar:

```sh
python3 tools/release.py publish-tree --release build/v1 --destination /absolute/path/to/ota-branch
```

Publicera `channel/` och `releases/` i **samma Git-commit** och pusha branchen till ditt publika repo. För nästa version:

```sh
# Redigera app/, kör sedan tester och bygg med ett högre versionsnummer.
sh tools/precommit.sh
python3 tools/release.py build --source app --output build/v2 --version 2 --private keys/release.pem
python3 tools/release.py verify --release build/v2
python3 tools/release.py publish-tree --release build/v2 --destination /absolute/path/to/ota-branch
```

Kör `git add channel releases`, `git commit` och `git push` i den separata OTA-checkouten. Kopiera aldrig hela arbetsrepot eller `build/usb-v1` dit. Behåll tidigare releasekataloger; byt inte innehåll under en befintlig digest.

Enheten läser:

```text
https://raw.githubusercontent.com/OWNER/REPO/ota/channel/manifest.json
https://raw.githubusercontent.com/OWNER/REPO/ota/channel/manifest.sig
https://raw.githubusercontent.com/OWNER/REPO/ota/releases/<manifest-sha256>/app_main.py
```

GitHub kan cachelagra filerna olika länge. Ett blandat manifest/signatur-par avvisas säkert och nästa försök sker senare. SHA-sökvägen binder nyttolasten till det signerade manifestet. Appen kontrollerar efter hälsoperioden och sedan en gång i timmen. Starta om för ett tidigare försök. Tillfälliga nätverksfel lämnar aktiv app intakt och försöks igen vid nästa intervall.

## Appkontrakt och självtest före commit

`app_main.selftest(ctx)` ska returnera exakt `True`. Kontrollera här exempelvis givarnas ID, nödvändiga importer, lagring och att utgångar kan hållas säkra. Undvik farliga sidoeffekter. Importer ska vara snabba och utan sidoeffekter.

`app_main.run(ctx)` kör huvudloopen och returnerar aldrig. Den ska:

- Anropa `ctx.feed()` efter meningsfulla hälsokontroller, oftare än watchdogens 8 s.
- Under provstart anropa `ctx.confirm()` först efter verkligt fungerande periferienheter och minst `CONFIRM_AFTER_MS`.
- Anropa `ctx.check_update()` bara när appen är bekräftad och har nätverk/klocka.

Självtestet körs på en ren omstart i kandidatens slot, innan OTA-commit. En misslyckad kandidat importeras aldrig in i den gamla appens process. Kompilering testar syntax, inte korrekt runtime-beteende. Exempelappens LED-test är en demonstration; byt ut det mot dina produktkrav.

## Tester och Git

```sh
sh tools/precommit.sh
# Valfritt lokalt Git-hook, från reporoten:
mkdir -p .git/hooks
printf '#!/bin/sh\nexec sh tools/precommit.sh\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

ZIP innehåller källkod utan `.git`-historik. Kör `git init` om du packar upp ZIP till en ny mapp. Hosttester använder tillfälliga testnycklar och testar den verkliga verifieraren. CI signerar inte produktionsreleaser och behöver inga hemligheter. Se [HARDWARE.md](docs/HARDWARE.md) för de obligatoriska tester som datorn inte kan ersätta.

## Återställning och begränsningar

- En reset, exception, watchdog eller strömavbrott under provstart ger rollback vid nästa boot. Även ett ofarligt strömavbrott förbrukar provförsöket.
- En vanlig exception i en bekräftad app kan falla tillbaka en gång till sparad tidigare slot. En watchdog-reset **efter bekräftelse** startar däremot den bekräftade appen igen. Detektering av godtyckliga produktfel kräver produktanpassad hälsologik.
- Vid nästa OTA återanvänds den gamla slotten, så den äldre fallbacken pensioneras innan skrivningen börjar.
- GP15 till GND vid hård reset ger USB-serviceläge utan app/watchdog. Om den betrodda roten inte kan köras behövs BOOTSEL och eventuell ominstallation/radering av filsystemet.
- A/B skyddar aldrig firmware, supervisor, rootinställningar, flashhårdvara eller ett helt förstört gemensamt filsystem.

Läs [arkitektur](docs/ARCHITECTURE.md), [säkerhet](docs/SECURITY.md) och [felsökning](docs/TROUBLESHOOTING.md) före användning i en produkt.
