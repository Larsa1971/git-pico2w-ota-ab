# Säkerhetsmodell

## Vad signeras?

Exakta UTF-8-bytes i `manifest.json`, inte ett återserialiserat JSON-objekt. Hostverktyget använder deterministisk JSON för reproducerbarhet. Detached `manifest.sig` är exakt 512 ASCII-hextecken (256 signaturbyte), utan radslut. Algoritmen är fast: RSASSA-PKCS1-v1_5 med SHA-256, RSA 2048/e=65537. Manifestet kan inte välja en annan algoritm/nyckel.

Verifieraren rekonstruerar **hela** PKCS#1-blocket: 00 01, rätt antal FF, 00, exakt SHA-256 DigestInfo och hash. Signaturer utanför modulus avvisas. Testerna korsverifierar med OpenSSL och provar ändrade data, fel signatur och ogiltiga storlekar. Publik modular exponentiering görs med MicroPython-bigints. Detta är en liten egenimplementation, inte en oberoende granskad kryptomodul. Anlita säkerhetsgranskning och mät på avsedd firmware inför produktionsbruk. Ingen konstanttidsgaranti ges; här hanteras endast offentliga data.

`version` är ett ökande positivt heltal, inte semver. `board` är `RPI_PICO2_W`; minimum MicroPython anges som tre heltal. Board-fältet kontrolleras mot målprotokollet, men autodetekterar inte den fysiska kortmodellen. Installatören måste välja rätt UF2 och verifiera kortet. Manifestet listar varje fil med `path`, `size`, `sha256`. Extra filer i en slot avvisas. Rootfiler och OTA-paket kan inte ingå i en uppdatering.

## Hot som hanteras

En angripare som ändrar GitHub-filer, payload eller trafik kan inte få godtycklig kod godkänd utan signeringsnyckeln. Hasharna binder filerna till ett autentiserat manifest. TLS används utan CA- eller värdnamnsverifiering. Därför kan nätverkstrafiken avlyssnas/manipuleras via aktiv MITM; den obligatoriska manifestsignaturen och filhasharna är den enda autentiseringen av uppdateringskod. Ingen GitHub-token skickas.

Äldre signerade OTA-versioner avvisas mot `floor`, inklusive tidigare misslyckade staged versioner. Intern rollback till redan betrodd aktiv/föregående slot är avsiktligt tillåten. Publicera en ny, högre version för att återinföra gammalt appinnehåll eller rätta en dålig release.

## Hot som inte hanteras

- Stöld av privat signeringsnyckel, en illvillig behörig signerare eller en signerad skadlig app. Appen kan skriva till hela filsystemet och anropa hårdvaran direkt.
- Fysisk åtkomst, USB/REPL, manipulering av publik nyckel, firmware eller status. `secret.py` är klartext på flash och Git-ignore är inte kryptering.
- Kryptografiskt skyddad antirollback/OTP-räknare. Statuschecksummor är oförseglade; en trasig ny post kan återgå till äldre floor. Strömavbrottssäkerheten och antirollbacken är därför best effort på ett gemensamt filsystem.
- Tillgänglighetsangrepp: blockerad GitHub/DNS, rate limiting, gamla cachefiler, manipulerad tid eller borttaget innehåll kan hindra uppdateringar.
- Secure boot, firmware-A/B eller skydd av bootloader/firmware. App-A/B hjälper bara så länge den delade grunden fungerar.
- Att appen är funktionellt korrekt efter den begränsade provperioden.

## Nyckelhantering och publicering

Generera egna nycklar; ingen demo-privatnyckel följer med. Håll signering utanför PR/obetrodda CI-jobb. Skicka aldrig `keys/`, `secret.py`, USB-image till OTA-branchen. Tillför ny publik signeringsnyckel via betrodd USB-provisionering; OTA-rotation stöds inte.

Releasefiler under `releases/<manifest-sha256>/` ska aldrig ändras. Publicera payload och channel i samma commit. GitHub raw använder inte ett transaktionellt snapshot över flera HTTP-anrop; signatur/hashfel vid cacheblandning avvisar uppdateringen säkert. Protokollet använder publik raw-branch, inte GitHub Release-assets och inga redirectkedjor. Om GitHub ändrar framing till exempelvis chunked krävs en granskad klientändring.

## Rapportering

Lägg inte hemligheter i publika issues. Rapportera sårbarheter privat till det egna projektets underhållare. Repoägaren behöver själv ange kontakt och incidentrutin innan repot publiceras.
