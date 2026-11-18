# Felsökning

**OSError(103) / ECONNABORTED:** TCP/TLS-anslutningen avbröts; felkoden pekar inte ensam ut orsaken. Kontrollera 2,4 GHz-Wi-Fi, DNS, internetåtkomst, att rätt kortfirmware används, RAM, TLS-stöd och loggen före felet. Detta repo använder GitHub via port 443, inte en lokal Mac-server. Denna variant har avsiktligt ingen CA-verifiering; kontrollera signaturerna och filhasharna.

**HTTP 404:** kontrollera OWNER/REPO/ref, publik läsbarhet och att `channel/` samt `releases/` finns på rätt branch. Öppna exakt raw-adress från README på datorn. Referensen måste ha enkelt namn utan slash.

**Invalid manifest signature:** fel publik nyckel, ändrat manifest/radslut, blandat cachepar eller felaktig signatur. Kör hostens verify mot exakt publicerad release; vänta på cache vid nylig publicering. Inga manuella JSON-ändringar efter signering.

**Ingen ny version hittas:** `version` måste överstiga beständig `floor`. En misslyckad provversion förbrukas avsiktligt. Gör nästa release med högre nummer. `floor` kan inspekteras via `Store().load()` i service-REPL.

**Watchdog-reset under uppdatering:** DNS/TLS/kompilering/RSA kan överstiga tidsbudgeten på verklig firmware. Mät i GP15-serviceläge. Behåll integritetskontrollerna. Anpassa filstorlekar, app och firmware efter mätning; anta inte att en ökad WDT-timeout stöds på porten.

**Provstart rollbackar trots fungerande app:** kontrollera att selftest returnerar True, att appen feedar efter hälsokontroller och bekräftar efter observationsperiod men före provtidsgränsen. Strömavbrott under trial räknas som misslyckat försök.

**Reset-loop i bekräftad app:** GP15 till GND, fysisk omstart och öppna USB-REPL. Rätta lokala inställningar eller provisionera en granskad signerad app via USB. Automatisk rollback för obegränsade framtida watchdogfel i bekräftad kod ingår inte.

**Båda statusposter trasiga:** kopiera inte en slumpmässig kandidat till active. Återprovisionera med en känd signerad release via USB. Säkerhetskopiera loggar först. Om firmware/rot är trasig behövs BOOTSEL och eventuell filsystemsåterställning. UF2-installation kan behålla data; anta inte att gamla filer försvinner automatiskt.
