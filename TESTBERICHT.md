# Prüfbericht — PiGrab, 12.11.2026

**Ergebnis: lokal vorbereitet; keine Pi-/VPN-Livefreigabe.** Der Pi ist ohne bekannte Zieladresse/Anmeldung nicht erreichbar nachgewiesen. Kein Installations-, Firewall- oder VPN-Befehl wurde auf einem Pi ausgeführt. Windows-Originalinstallation und vorhandene Downloads wurden nicht verändert. Die Forderung nach wechselnden öffentlichen WLANs und parallel laufendem Proton ist im Schutzkonzept berücksichtigt; die praktische Koexistenz bleibt offen.

## Referenz gelesen und abgeglichen

`C:\Tools\dl\grab.ps1`, `config.ps1`, `grab.cmd`, `README.txt` vollständig gelesen. Ergänzend Sicherheitskorrektur/Vorschau-Testbericht und relevante Stellen in Prüfbericht 8 geprüft. Nicht alle alten Protokolle oder alten Medien wurden erneut geprüft. Folgende Original-SHA256 wurden zu Beginn und am Ende identisch festgestellt:

| Datei | SHA256 |
|---|---|
| grab.ps1 | `5417ED21E99739146F520FE9F91AE0BC1932DB50BAF75646432FC3A644A005AF` |
| config.ps1 | `20148EE4A5D5176CC723096F2D56173929680B9BAB1FBCB4140AA816271445EE` |
| grab.cmd | `8EFD5A9EA5DA1AA745FE878402BA92854A53C5A69028A76D95E2B5618EB629AF` |
| README.txt | `36F66D5762C28813D7F35922263AD1057E394FDBC8DDA35AD438728F52678569` |

Am aktuellen Code beobachtet:

- Queue-Vorschau hat eine vorangestellte Prüfung/Probe; jeder echte Download hat eigene Prüfungen. Vorschau übergibt Namen und Originalseitenlinks. VOE löst frisch auf. Netzwerk-/Probefehler stoppen die Queue.
- `Test-PrivacyState` betrachtet bestimmte physische Adapter und filtert virtuelle/TAP/WireGuard-Beschreibungen. Die Aussage in älteren Berichten, alle Adapter seien berücksichtigt, gilt damit nicht für den aktuellen Code.
- Die aktuelle Remux-Kommandozeile übernimmt Untertitel und Anhänge. Ein älterer Bericht nennt noch deren Ausschluss; diese Aussage ist überholt. Die neue Portierung prüft zusätzlich Streamanzahl/Codecs und Anhangsdaten.
- Der allgemeine `Get-QueueItemInfo`-Generic-Retry hatte im gelesenen Code keine eigene Netzwerkprüfung. Die Portierung prüft vor diesem Retry erneut.
- Die bestehenden IP-Snapshots prüfen keinen dauerhaft erzwungenen Prozesspfad. Unterschiedliche Netzwerkbibliotheken/Proxyeinstellungen und der außerhalb des Skripts vorausgesetzte Kill-Switch sind kein umfassender Sicherheitsnachweis. Die Portierung verlangt daher die eigene Netzsperre.
- Windows akzeptiert im Statuspfad einen nichtleeren IP-String. Die Portierung validiert passende globale IP-Adressen. Die Windows-Mindestgröße über 1 MiB wurde durch „vorhanden/nichtleer und Containerprüfung“ ersetzt, damit kleine zulässige Videos nicht allein an der Größe scheitern.

## Lokale Umgebung und Befehle

Windows 11, gebündeltes CPython 3.12.14, isolierte Test-venv im Projekt unter `work/testenv`. Eigene yt-dlp-Installation 2026.10.26, Beautiful Soup 4.14.3, SoupSieve 4.1, typing_extensions 4.16.0; gesperrte reine Wheels vorab geprüft. Bereits vorhandene `C:\Tools\dl\ffmpeg.exe` und `ffprobe.exe`, Version 9.0.2-essentials_build-www.gyan.dev, wurden ausschließlich mit neu erzeugten lokalen Testmedien aufgerufen. Keine bestehenden Downloads als Testmaterial benutzt.

Aus dem Codex-Projektordner in PowerShell:

```powershell
$env:PYTHONUTF8='1'
$env:PIGRAB_TEST_FFMPEG='C:\Tools\dl\ffmpeg.exe'
$env:PIGRAB_TEST_FFPROBE='C:\Tools\dl\ffprobe.exe'
$env:PIGRAB_TEST_YDL=(Resolve-Path -LiteralPath work\testenv\Scripts\yt-dlp.exe).Path
& .\work\testenv\Scripts\python.exe -m unittest discover -s outputs\pi-grab\tests -v
& .\work\testenv\Scripts\python.exe -m pip check
& .\work\testenv\Scripts\python.exe -m compileall -q outputs\pi-grab
& .\work\testenv\Scripts\python.exe outputs\pi-grab\grab.py --skip-check 'https://example.org/video.mp4'
```

Der letzte Befehl verweigert Windows mit `ID=PLATFORM_UNSUPPORTED`, **Exit 1**, bevor eine öffentliche Anfrage erfolgt. `pip check`: keine defekten Abhängigkeiten, Exit 0. Syntaxprüfung: Exit 0. Erste Fassung: 28 Tests, 27 erfolgreich, 1 Linux-spezifisch übersprungen. Aktuelle Fassung 1.1: **33 Tests, 32 erfolgreich, 1 Linux-spezifisch übersprungen, Suite-Exit 0**. Der aktuelle Lauf ist im mitgelieferten `test-output.txt` festgehalten.

## Ergänzung 1.1: einfache Bedienung und Speicherverbrauch

Auf Wunsch des Nutzers wird der Pi hauptsächlich als Downloader geplant. Ein eigener Proton-WireGuard-Tunnel genügt hierfür; ein zusätzlicher Host-Proton-Client wird nicht vorausgesetzt und auch nicht automatisch verändert. Andere Host-Programme sind dadurch nicht automatisch VPN-geschützt. Details und noch zu messende Optimierungen: `OPTIMIERUNG.md`.

Lokal geändert: Streaming-Serialisierung der ohnehin erforderlichen privaten Medieninfo-Datei, Freigabe ihres Python-Objektbaums vor Transfer, direkte Liveausgabe ohne aufbewahrte Diagnosekopie, kurzer root-eigener `pigrab`-Starter bei der späteren Linux-Installation. Netzguard, Konfiguration und Abhängigkeitssperrdatei wurden gegen das ursprüngliche 1.0-Archiv geprüft und sind bytegleich. Alle vier Windows-Originalhashes sind erneut unverändert.

Fünf neue Tests prüfen: sichtbare Liveausgabe von mehr als 500.000 Zeichen ohne Rückhaltekopie; tatsächliche Freigabe des Medieninfo-Objekts per schwacher Referenz bei weiterhin funktionierendem Retry aus der identischen privaten Datei; unveränderte Argumentgrenzen und verpflichtender Guard im Starter; Verweigerung eines Starts als root; lokale Hilfe ohne sudo/Netzwerk. Alle bisherigen lokalen Medien-/Negativtests wurden erneut ausgeführt. Ein Vorlauf scheiterte am gesperrten Socketzugriff der Codex-Umgebung (`WinError 10013`, auch für 127.0.0.1); nach Freigabe des Testzugriffs lief die komplette Suite mit Exit 0. Es wurde kein VPN dafür abgeschaltet oder geändert.

Keine gemessene RAM-/Geschwindigkeitszusage für den Pi. Die 33 Tests bleiben Windows-/Loopback-/Simulationsnachweise. Neu UNGETESTET ist auch die Installation/Ausführung von `/usr/local/bin/pigrab` unter Linux; sie verlangt weiterhin die normale sudo-Anmeldung. Die Freigabe des Objektbaums im Hauptprozess sagt nichts über den RAM-Spitzenverbrauch des später gestarteten yt-dlp-/FFmpeg-Prozesses aus.

## Was tatsächlich getestet wurde

| Fall | Art und Ergebnis | Code/Nachweis |
|---|---|---|
| Direkte MP4 | Echter yt-dlp-Transfer über eigenen Loopback-HTTP-Server, Remux und Prüfung, Name mit Umlaut/Shellzeichen | Erfolg; yt-dlp/FFmpeg 0, Test grün |
| HLS | Selbst erzeugte Playlist/Segmente über Loopback; echte yt-dlp-/FFmpeg-Prozesse, TS nach MKV | Erfolg; keine Videokodierung im Downloadpfad |
| Queue gültig/kaputt | Echter lokaler guter Link plus absichtlicher HTTP-404-Link | 1 Datei veröffentlicht, ein Fehler; Queue-Rückgabe 1 |
| Queue Netz-/Probeabbruch | Simulierte Netzwerk-/Probefehler, kein weiterer Eintrag/kein Auflösen nach Probeversagen | Fehlerklasse 2, Queue-Rückgabe 2; keine Veröffentlichung |
| Vorschau | Simulierte Auflösung/Input, Reihenfolge Probe vor Auflösung, nur ursprünglicher Link/Name an Download | Gemischte Queue 1, kein signierter Vorschau-Link weitergereicht |
| Mullvad/ipapi | Dokumentierte/aktuell beobachtete Antwortformen als Fixtures, exakt 3+1 Fallbackversuche, unbrauchbarer Status | Fehlerklasse 2 bei Ausfall; keine Positivfreigabe |
| Länder/Organisation | Heimatland, Blockliste, fehlende Daten trotz Force | Fehlerklasse 2 |
| DNS | Simuliertes dig mit CNAME, IP-Validierung und genau einer Geolokalisierung | Erfolgreich; kein realer Pi-DNS-Leaktest |
| IP-Wechsel | Simulierter Wechsel vor/nach Transfer | Fehlerklasse 2; keine fertige Datei/keine letzte IP |
| Unicode/Shellzeichen | Umlaute, Emoji-Längengrenze, `&`, `$()`, Backticks, Semikolon, Traversalzeichen | Zeichen als Daten; echter Kindprozess sieht unverändertes Argument und Exit 7 |
| Kollisionen/Parallelität | 12 Veröffentlichungen aus 4 echten lokalen Workerprozessen | 12 unterschiedliche Dateien; keine vorhandene Ausgabe ersetzt |
| Range-/Retry | Simulierter HTTP-416-/Range-Transferfehler | Ein frischer Retry ohne beide Beschleuniger, Teilstand entfernt, Prüfpunkt/VOE-Pflichtheader kontrolliert |
| MP4/MKV/AVI | Echte FFmpeg-/ffprobe-Remuxläufe | Alle drei erfolgreich |
| Streams | Echte MKV mit 2 Videos, 2 Audios, Untertitel und Anhang | Ergebnis 1 Video, 2 Audios, Untertitel und gleicher Anhangshash |
| Unerlaubte Tags | Synthetische Werte und echte Datei mit personalisierten Tags | Fehlerklasse 5, keine Freigabe beliebiger encoder/handler-Werte |
| Timeout | Echter 20-s-Testprozess nach 0,2 s beendet, nicht erfolgreicher Exit; Probeparameter 60 s und Exit-/Dateikontrolle simuliert | Timeout erkannt; Probe-Fehlerklasse 2, Datei entfernt |
| Aufräumen | Normale Fehlerpfade und alter eigener Arbeitsordner | Fehlerreste entfernt, alte Anzahl ausgegeben |
| Admin-Profil | Datenparser mit Hooks, Host-Stub-DNS, Splitrouten und Endpoint-Hostname | Abgelehnt; keine tatsächlichen Adminsystemaufrufe |
| Netzsperren-Soll | Statische enge Regeln/Profilbehandlung, keine physische Interfacefreigabe | Quell-/Unittestprüfung; **kein Kernel-Ausfalltest** |

Die Netzwerkchecks in den Medienprüfungen sind ausdrücklich durch eine Testklasse ersetzt; der HTTP-Server bindet ausschließlich 127.0.0.1. Das Programm besitzt keinen entsprechenden produktiven Test-Bypass. Windows nutzt für die Entwicklung eine atomare, nicht überschreibende Windows-Umbenennung; **Linux-Hardlink-Veröffentlichung, flock und Symlinkabwehr sind dadurch nicht getestet**. Windows-Hardlinks waren in dieser Sandbox verweigert, daher wird deren Test nicht als Linux-Nachweis ausgegeben. Frühe Testläufe deckten Container-Handlerwerte und native HLS-TS-Rohdaten auf; beides wurde gezielt korrigiert und erneut getestet.

## Offen / UNGETESTET

- Tatsächlicher Pi: Modell/RAM/OS/32- oder 64-Bit/CPU, Kernel, Programmversionen, Dateisystem, freier Platz, Zielmedium.
- Installation und ARM-Ausführung. Lokales WSL meldete `Wsl/E_ACCESSDENIED`; Docker-Daemon war nicht erreichbar. Es wurde keine Ersatz-Linux-Installation gestartet oder installiert.
- Echter SSH-Zugang, Hostfingerprint, dauerhafter Fernzugriff bei fremden WLANs. Siehe `VERBINDUNG.md`.
- Alle privilegierten Linux-Schritte: Namespace/WireGuard/nft-Sollvergleich, private Mounts, Resolver-Symlinks, Capability-Abwurf, root-Datenschutz, vollständige Kindprozess-Pfaderzwingung.
- Echte IPv4-/DNS-Policy und IPv6-Sperre auf dem Pi; Host-Proton-Koexistenz, Split-Tunneling/Kill-Switch, DNS-Verhalten aller Prozesse.
- Frisch erreichbare VOE-Adresse und Live-VOE-Transfer auf ARM. Der frühere Bericht nennt `https://voe.sx/e/av3hnz6t21bm`; dieser alte Beispiel-Link wurde nicht als aktuell erreichbar ausgegeben oder als Portierungstest gewertet.
- Internet-Direktdatei/HLS, Live-Queue und realer HTTP-Range-Serverfehler auf dem Pi. Lokale synthetische Medien sind kein Nachweis für bestimmte Videoseiten.
- Linux-aktive-lock-/Symlinktest (der eine Skip), Linux-Hardlink/fsync-Verhalten und Stromausfall/harter Prozessabbruch; außer den beschriebenen normalen Fehlerpfaden.
- Echter WireGuard-Ausfall, paralleler Proton-Ausfall, WLAN-Roaming/Captive Portal, Neustart-Recovery, langlaufende Transfers und Leistung/RAM-/Speicherverbrauch des Pi.

## Konkreter Abnahmeplan auf dem Pi

1. Gesicherten lokalen/SSH-Zugang und Rückweg herstellen, `inventory.py` ausführen, offene Gerätedaten ergänzen. Host-Proton-Konfiguration lokal prüfen, keine Schlüssel protokollieren. Genügend freie Ablage prüfen.
2. Gemäß README separat installieren. Automatisierte Suite auf Linux ausführen; **kein Skip** bei fehlenden Pflicht-Binaries stillschweigend als Erfolg behandeln. Kernel-/nft-Sollabweichungen untersuchen, niemals durch eine Accept-Regel oder abgeschaltete Prüfung übergehen.
3. Eigenes Profil einrichten, `netguard.py status`. Im geschützten echten Start die Probe/Statusregeln durchführen. Alle Beobachtungen mit Datum, Versionen und tatsächlichem Shell-Exit-Code festhalten.
4. Öffentliche Direktdatei über den normalen Einzelaufruf testen, beispielsweise die konfigurierte Samplelib-Datei. Danach selbst kontrollierte öffentliche HLS-Quelle und frisch erreichbare, berechtigt zugängliche VOE-Seite. Titel, Header, Streams, Metadaten und Ergebnisdatei prüfen. Kein erneutes Aufrufen einer bereits aufgelösten alten signierten Adresse.
5. Interaktive Queue mit gutem und absichtlich fehlendem Link. Erwartet: guter Eintrag erfolgreich, schlechter übersprungen, Gesamt 1. Gesondert gezielt verweigerte Netz-/Probeprüfung: gesamte verbleibende Queue abgebrochen, Gesamt 2, keine Veröffentlichung.
6. **Nur mit lokalem Rückweg:** In einer zweiten lokalen Verwaltungssitzung ausschließlich `wg0` in `grabvpn` während eines eigenen Testtransfers heruntersetzen (`sudo ip -n grabvpn link set wg0 down`). Niemals dafür das Host-WLAN oder paralleles Host-Proton über die einzige SSH-Verbindung trennen. Gleichzeitig physisches Interface auf unverschlüsselte Video-/DNS-Zielverbindungen beobachten; verschlüsselte WG-UDP-Außenpakete unterscheiden. Ergebnis darf nicht erscheinen. Tunnel anschließend nur im eigenen Namespace wieder hochsetzen und mit Originalseitenlink neu beginnen.
7. Wiederholung mit komplett entferntem eigenen WG-Interface/fehlendem Namespace kontrolliert planen. Startup muss verweigern. Je nach Fall kann ein Transfer zunächst Timeout/Downloadfehler 4 melden; der nächste fehlgeschlagene Netzprüfpunkt ist 2. Das ist kein Beweis allein aus dem Fehlercode: tatsächlicher Paketpfad ist entscheidend.
8. Erst danach kontrollierten WLAN-Wechsel/Neustart und gegebenenfalls Host-Proton-Ausfall bei vorhandenem lokalem Zugang prüfen. SSH-Rückweg separat testen. Bootdienst erst nach bestandener Gerätekonfiguration entwerfen.

Mitgelieferte Tests/Quellen ermöglichen diese Abnahme, ersetzen sie aber nicht. Kein pauschales Urteil „anonym“, „alles sicher“ oder „VPN-Leaks ausgeschlossen“.
