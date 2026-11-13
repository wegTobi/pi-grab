# PiGrab — lokale Raspberry-Pi-Portierung

Stand: 12.11.2026, Fassung 1.1. Lokal vorbereitet und getestet; **noch nicht auf einem Raspberry Pi installiert oder freigegeben**. Ein erreichbarer Pi/SSH-Zugang liegt nicht vor. Die bisherigen Windows-Dateien, Downloads und VPN-Einstellungen wurden nicht verändert. Ergebnisse und Grenzen stehen in `TESTBERICHT.md` und `SECURITY.md`. Vereinfachungen für einen hauptsächlich als Downloader genutzten 2-GB-Pi: `OPTIMIERUNG.md`.

## Was enthalten ist

Python steuert yt-dlp und FFmpeg mit getrennten Argumenten, echten Exit-Codes und Zeitgrenzen. Python ist auf ARM wartbar und vermeidet eine zusätzliche PowerShell-Laufzeit. Die Konfiguration ist TOML, kein ausführbarer Code. Alle vier Python-Abhängigkeiten sind als architekturunabhängige Wheels mit SHA256-Sperrdatei enthalten. Windows-EXE-Dateien gehören nicht zur Lieferung.

`grab.py` enthält Einzelaufruf, interaktive Queue/Vorschau, Netzwerkprüfungen, Probe, Wiederholung, Remux, Metadatenkontrolle und Veröffentlichung. `voe_resolver.py` verwendet ausschließlich Auflösungsfunktionen aus einem festgehaltenen Stand von MPZ-00/voe-dl. `netguard.py` richtet einen eigenen Linux-Netzwerkbereich ein und startet das Programm darin ohne Administratorrechte. `inventory.py` sammelt die noch fehlenden Geräteangaben lokal und ohne öffentliche Anfragen.

## Voraussetzungen auf dem Pi

- Raspberry Pi 4, vorzugsweise 64-Bit-Raspberry-Pi-OS; tatsächliches Modell/RAM/OS sind noch unbekannt. Keine Neuinstallation ohne vorherige Bestandsaufnahme.
- Python **ab 3.11.5** (durch die gesperrte SoupSieve-Version bedingt), `venv`, FFmpeg/ffprobe, curl, dig, iproute2, nftables, wireguard-tools und util-linux (`unshare`, `mount`, `setpriv`). Debian-/Pi-OS-Pakete liefern ARM-Versionen. Auf einem älteren System nicht ungeprüft das System-Python ersetzen.
- Ein eigener **Proton-WireGuard-Export** mit numerischer öffentlicher Endpoint-IP, IPv4-Tunneladresse und VPN-DNS. Ein nichtdeutscher Exit muss zusätzlich zur bestehenden Organisations-Positivliste passen. Der Export bleibt lokal auf dem Pi; keine Schlüssel in Chats oder Testberichte kopieren.
- Für den hauptsächlich als Downloader genutzten Pi genügt dieser eine Proton-WireGuard-Tunnel; dafür ist keine zusätzliche Proton-App/Host-VPN-Verbindung nötig. Er schützt die gestarteten Downloadprozesse. Andere Host-Programme sind damit nicht automatisch VPN-geschützt. Ein bereits parallel laufender Proton-Client bleibt unangetastet. Dessen Kill-Switch kann den eigenen Tunnel blockieren; dann scheitert der Start/Probe geschlossen. Keine automatische Ausnahme wird hinzugefügt. Läuft er über Host-Proton, benötigt der zusätzliche Tunnel eine weitere mögliche Verbindung im Konto und kann doppelt getunnelt sein.
- Lokale POSIX-Ablage, vorzugsweise ext4, ausreichend Platz für Rohdatei **und** Remux (mindestens ungefähr doppelte Videogröße plus Reserve). FAT/exFAT/unsichere Netzlaufwerke eignen sich nicht für die hier verwendeten Hardlinks/Locks/Rechte.

Die offizielle [Proton-Anleitung](https://protonvpn.com/support/wireguard-linux) beschreibt WireGuard auf Linux; ein konkreter paralleler GUI-/CLI-Client auf deinem ARM-System ist damit noch nicht nachgewiesen. Offizielle Quellen und geprüfte Versionen: `SOURCES.md`.

## Erst Verbindung und Gerät prüfen

`VERBINDUNG.md` beschreibt die fehlenden Angaben und den Betrieb in wechselnden öffentlichen WLANs. Sobald eine gesicherte SSH-Verbindung besteht, diesen Projektordner auf den Pi kopieren. Den SSH-Hostschlüssel über einen unabhängigen Weg prüfen; keine Option zum Überspringen der Hostschlüsselprüfung verwenden.

Im kopierten Projektordner auf dem Pi, als normaler Benutzer:

```sh
python3 inventory.py > pi-inventur.txt
python3 --version
```

Die Inventur enthält lokale Netzwerkadressen und Gerätenamen. Vor einer Weitergabe prüfen. Sie liest keine WireGuard-Schlüssel. Dateisystem und Platz der tatsächlich vorgesehenen Ablage zusätzlich mit `df -hT /pfad/zur/ablage` und `findmnt -T /pfad/zur/ablage` prüfen. Modell, RAM, OS, Architektur, Programmversionen, VPN, DNS, IPv6, Regeln und Speicher müssen anschließend im Testbericht ergänzt werden.

## Installation — erst auf dem geprüften Pi ausführen

Diese Befehle wurden hier **nicht auf dem Pi ausgeführt**. Die Paketinstallation betrifft offizielle Bezugsquellen und geschieht im Host-Netz; dessen Proton-Schutz vorher kontrollieren. Die späteren Videozugriffe sind ausschließlich im eigenen Namespace erlaubt.

```sh
sudo apt update
sudo apt install python3 python3-venv ffmpeg curl dnsutils iproute2 nftables wireguard-tools util-linux
sudo python3 install.py
sudo python3 -m venv /opt/pi-grab/venv
sudo /opt/pi-grab/venv/bin/python -m pip install --no-index --find-links /opt/pi-grab/wheels --require-hashes -r /opt/pi-grab/requirements.lock
sudo /opt/pi-grab/venv/bin/python -m pip check
sudoedit /opt/pi-grab/config.toml
```

`install.py` verweigert eine bestehende `/opt/pi-grab`-Installation oder einen bestehenden `/usr/local/bin/pigrab`-Befehl. Es kopiert ausschließlich dieses Projekt, setzt root-Eigentum und lädt nichts herunter. Der neue Starter wird als root-eigene Datei `/usr/local/bin/pigrab` angelegt. Keine sudoers-Regel, kein Autostart und keine Änderung der PATH-Variable. Ein späteres Update erfolgt erst bei beendeten eigenen Instanzen mit vorheriger Sicherung; dieses Paket überschreibt keine laufende Installation automatisch.

In `config.toml` kann `storage` auf eine eigene lokale Ablage zeigen. `~` bezeichnet den beim Start angegebenen Downloadbenutzer. Voreinstellung:

```text
~/Videos/PiGrab/finished/      fertige Videos
~/Videos/PiGrab/.work/         private Arbeitsdaten je Eintrag
~/Videos/PiGrab/.state/        .last_exit_ip
```

Die Ablage gehört diesem Benutzer und darf nicht fremd beschreibbar sein. Symlinks in der Ablagekette werden abgelehnt. Arbeits- und Ausgabeordner müssen dasselbe Dateisystem verwenden.

## Proton-Tunnel einrichten

Einen **eigenen** WireGuard-Export aus dem [Proton-Konto](https://protonvpn.com/support/wireguard-configurations) lokal als beispielsweise `proton-download.conf` bereitstellen. Nicht dasselbe aktive Profil gleichzeitig für zwei Clients verwenden. Nur dieses Profil wird verarbeitet; bestehende Proton- oder Netzwerkprofile werden nicht verändert.

```sh
sudo install -m 600 -o root -g root proton-download.conf /etc/wireguard/pi-grab.conf
sudo /opt/pi-grab/venv/bin/python -I /opt/pi-grab/netguard.py setup --profile /etc/wireguard/pi-grab.conf
sudo /opt/pi-grab/venv/bin/python -I /opt/pi-grab/netguard.py status
```

Der Parser erlaubt genau ein Interface und einen Peer. `PostUp`, `PreUp`, `PostDown`, `Table`, `SaveConfig`, fremde Hooks, zusätzliche Routen und Hostnamen als VPN-Endpoint werden abgelehnt. `Address`, `DNS`, optional `MTU` und die nötigen WireGuard-Schlüssel werden als Daten verarbeitet; es läuft **kein** `wg-quick` mit Profilbefehlen. Aus einem dualen Profil wird nur IPv4 übernommen; das wird durch die gesamte IPv6-Sperre abgesichert.

`setup` erzeugt ausschließlich `grabvpn`, kurzzeitig `grabwg0` im Host, danach `wg0` in `grabvpn`, dessen Firewall/Routen, `/etc/netns/grabvpn/{resolv.conf,nsswitch.conf}` und `/var/lib/pi-grab-netguard/namespace.id`. Die einzige Route im neuen Bereich führt über WireGuard. Host-Routen, Host-Firewall, WLAN, SSH und der parallele Proton-Client werden nicht umkonfiguriert. Der verschlüsselte WireGuard-UDP-Socket bleibt im Host. Die Konstruktion folgt der [WireGuard-Namespace-Dokumentation](https://www.wireguard.com/netns/).

Die aktuelle Einrichtung ist bis zum Neustart aktiv. Es gibt absichtlich noch keinen ungeprüften automatischen Boot-Dienst. Nach Neustart bleibt ein Download ohne erneute Einrichtung gesperrt. `/etc/netns/grabvpn` und der Verwaltungszustand können einen Neustart überleben; vor erneuter Einrichtung alte Zustandsdateien ausschließlich nach Prüfung entfernen, siehe Rückweg unten.

## Start und Bedienung

Nach abgeschlossener einmaliger Einrichtung reicht als normaler Pi-Benutzer:

```sh
pigrab
pigrab 'https://example.org/video.mp4' 'Grüße & Folge 01'
pigrab --help
```

Der kurze Starter ermittelt die echte Benutzerkennung und ruft denselben `netguard.py run`-Pfad über sudo auf. Die normale sudo-Passwortabfrage kann erscheinen. Er verändert weder VPN noch Prüfungen und richtet keine fehlende Netzsperre automatisch ein. `pigrab --help` funktioniert auch ohne sudo/Tunnel. Aufrufargumente werden unverändert als getrennte Argumente übergeben. Installation und Ausführung dieses Linux-Starters sind noch auf dem Pi zu prüfen.

Der bisherige vollständige Aufruf bleibt für die Diagnose verfügbar:

`BENUTZER` durch den normalen Pi-Benutzer ersetzen. Für Ausgaben auf einer externen Platte muss dieser Benutzer Schreibrechte haben.

```sh
sudo /opt/pi-grab/venv/bin/python -I /opt/pi-grab/netguard.py run --user BENUTZER --
sudo /opt/pi-grab/venv/bin/python -I /opt/pi-grab/netguard.py run --user BENUTZER -- 'https://example.org/video.mp4' 'Grüße & Folge 01'
```

Ohne URL: ein Link je Zeile; leere Zeile, `fertig` oder `ende` beendet die Eingabe. Zuerst erfolgen Netzwerkprüfung und höchstens 60 Sekunden Probe. Danach werden Namen und Medieninformationen ermittelt; die Vorschau zeigt Namen oder konkrete Fehlerklassen. Enter startet gültige Einträge, `abbrechen` verwirft die Liste. Manuelle Namen gehen vor. Die Vorschau speichert ausschließlich Namen und ursprüngliche Seitenlinks, keine signierten Medienadressen. Namen können bei Veröffentlichung einen Kollisionssuffix erhalten; die Vorschau reserviert noch keine Dateinamen.

Jeder echte Eintrag prüft erneut Netzwerk/Probe, löst frisch auf, prüft unmittelbar vor dem Transfer erneut und vergleicht die IPv4. Nach Transfer, Remux und Tagprüfung wird erneut geprüft. Bei einem erkannten Wechsel gibt es keine Veröffentlichung; ursprünglichen Seitenlink neu starten. Vor einem kompatiblen Wiederholungsversuch wird nochmals geprüft. Dazwischen werden keine zusätzlichen vorbereitenden externen Abfragen eingeschoben. Der Transfer selbst darf die für HLS/Medien erforderlichen Manifest-/Segmentanfragen stellen.

Für allgemeine Seiten ermittelt yt-dlp die Medieninformationen vor dem letzten Prüfpunkt; nur für den laufenden Eintrag werden diese privat als `media.json` zwischengespeichert und mit `--load-info-json` an den Transfer übergeben. Bei `Unsupported URL` wird einmal der generische Extraktor für die Auflösung versucht. Der Transfer beginnt mit `10M` HTTP-Chunks und vier Fragmenten. Bei einem Fehler folgt einmal ein frischer Versuch ohne beide Optionen. Interne Netzwerk-Retries sind auf null gesetzt; Wiederholungen sind damit sichtbar steuerbar. Alte Teilstände werden vorher vollständig entfernt.

VOE: `/e/[a-z0-9]+` wird unabhängig vom ursprünglichen Host auf `https://voe.sx` umgeschrieben. Weiterleitungsseiten müssen HTTPS und in `voe_hosts` enthalten sein. Unbekannte Hosts werden nicht automatisch freigeschaltet. Keine CAPTCHA-/DRM-/Zugriffsschutzumgehung. Der Resolver führt kein JavaScript aus, speichert keine Debug-Seiten und lädt kein Video. yt-dlp transferiert anschließend stets mit `Referer: https://voe.sx/` und dem festen bisherigen User-Agent. Beides ist eine Kompatibilitätseinstellung, kein Anonymitätsnachweis.

## Container und Metadaten

MP4/MOV werden zu `.mp4`, Matroska/WebM zu `.mkv`, AVI zu `.avi`. **Dokumentierte Erweiterung für HLS:** MPEG-TS-Rohdaten werden unter Beibehaltung aller ausgewählten Streams verlustfrei nach MKV remuxt. Die TS-Rohdatei wird nie veröffentlicht. Andere Container werden ausdrücklich abgelehnt.

FFmpeg kopiert erstes Video, sämtliche enthaltenen Audiospuren, Untertitel und Anhänge, entfernt Kapitel sowie globale und Stream-Metadaten und setzt neutrale Sprache/Handler/Anhangsnamen. Weitere Videospuren werden ausgeschlossen. Nicht integrierte externe Untertitel werden nicht zusätzlich gesucht. Es gibt keine erneute Video-/Audiokodierung und keine stille Untertitelkonvertierung. Ein unvereinbarer Stream führt zum Fehler. Das Ergebnis wird auf Streamanzahl und Codecs geprüft; bei Anhängen werden SHA256 der Anhangsdaten und Größe verglichen, da neutrale MIME-Werte die Codec-Erkennung verändern können.

Die Tagprüfung kontrolliert eng begrenzte **Werte und Kontext**, nicht nur Schlüsselnamen. Unbekannte neue FFmpeg-Strukturwerte scheitern geschlossen, bis sie gezielt untersucht wurden. Details: `SECURITY.md`.

## Ausnahmen und Fehlercodes

Beide Ausnahmen sind standardmäßig aus und werden deutlich ausgegeben:

- `--force`: umgeht ausschließlich die IPv4-/DNS-Organisationspositivliste. Heimatland, Blockliste, fehlende Angaben und verpflichtende Netzsperre bleiben wirksam.
- `--skip-check`: überspringt IP-/DNS-/Probe- und IP-Stabilitätskontrollen. **Die Namespace-Sperre bleibt Pflicht.** `.last_exit_ip` wird hierbei nicht aktualisiert. Das ist enger als die Windows-Ausnahme; ein ungeschützter Normalnetz-Start ist auch damit nicht möglich.

Fehler: `FEHLER: ID=...; EXIT_CODE=...; MESSAGE=...`. Codes: `0` Erfolg, `1` Eingabe/Config/Container/Abbruch, `2` Netzwerk/Probe, `4` Download/Auflösung, `5` Remux/Metadaten. Gemischte Queue: `1`; Netzwerk-/Probefehler stoppen alles mit `2`. Schlusszeile: `Warteschlange: X erfolgreich, Y übersprungen, Z abgebrochen`. Einzelaufrufe bewahren den spezifischen Fehlercode.

Native Ausgabe wird während der Laufzeit weitergereicht; vollständige URLs werden aus dieser Anzeige entfernt. Sie wird nicht zusätzlich als Diagnosekopie aufbewahrt. Bei Live-Prozessen gibt es alle 30 Sekunden `läuft noch, X von Y`. Kein dauerhaftes Anwendungslog ist voreingestellt. Dateinamen, Shellverlauf, private Arbeitsreste und die letzte Exit-IP bleiben lokale Nutzungsspuren.

## Rückweg, Neustart und Tunnelwechsel

Erst eigene Downloads normal mit Strg+C beenden. Dann:

```sh
sudo /opt/pi-grab/venv/bin/python -I /opt/pi-grab/netguard.py down
```

`down` verweigert aktive Prozesse und abweichende Regeln. Es löscht ausschließlich den benannten eigenen Namespace und exakt die eigenen Zustandsdateien, kein Host-Proton-Profil. Anschließend kann mit einem eigenen neuen Profil wieder `setup` ausgeführt werden. Ein Serverwechsel geschieht zwischen Downloads, nicht mit einer alten signierten Medienadresse mitten im Transfer.

Nach einem Neustart existiert möglicherweise nur noch der persistente Zustand. Dann gibt es keinen Namespace mehr, den `down` löschen könnte. Lokal zuerst `sudo ip netns list` und `sudo ip link show grabwg0` prüfen. **Nur wenn `grabvpn`/`grabwg0` fehlen, keine eigenen Prozesse laufen und die Verzeichnisse ausschließlich die oben genannten eigenen Dateien enthalten**, diese Dateien mit vollständigen Pfaden einzeln entfernen und die nun leeren Verzeichnisse mit `rmdir` entfernen. Keine rekursive Pauschallöschung, kein `ip route flush`, kein `nft flush ruleset`. Danach `setup` erneut ausführen. Ein automatischer Neustart-/Recovery-Dienst ist erst nach den Pi-Tests sinnvoll.

## Tests auf dem Pi nachholen

Die mitgelieferten automatisierten Tests verwenden ausschließlich lokale Testmedien und Loopback-HTTP. VPN-Abfragen sind dort **simuliert**; das ist kein Kill-Switch-Test:

```sh
/opt/pi-grab/venv/bin/python -m unittest discover -s /opt/pi-grab/tests -v
```

Danach echte geschützte Direktdatei-/HLS-/VOE-Downloads, Queue und kontrollierten Ausfall gemäß `TESTBERICHT.md` prüfen. Vor dem VPN-Ausfalltest ist ein lokaler Wiederzugang oder unabhängig geprüfter Fernzugang erforderlich. Keine hostweiten VPN-Verbindungen oder das WLAN über eine ungesicherte einzige SSH-Verbindung trennen.
