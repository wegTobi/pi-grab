# Einfacher Betrieb auf dem Raspberry Pi 4 mit 2 GB

Entscheidung vom 12.11.2026: Der Pi wird hauptsächlich für dieses Downloadwerkzeug genutzt. Ziel ist weniger Verwaltungsaufwand und geringerer Ressourcenverbrauch bei unveränderten Schutzanforderungen. Keine pauschale Anonymitätszusage; eine Installation und Messung auf dem Pi stehen weiterhin aus.

## Empfohlener Aufbau

```text
WLAN und SSH im normalen Pi-System
                 |
        verschlüsselter WireGuard-Verkehr
                 |
Downloadbereich: genau ein Proton-WireGuard-Tunnel
                 |
        Python -> yt-dlp -> FFmpeg
```

Ein eigener Proton-WireGuard-Tunnel im vorhandenen isolierten Netzwerkbereich reicht für den Downloader aus. Eine zusätzliche Proton-App im Host ist dafür nicht nötig. Das spart eine weitere VPN-Verbindung und gegebenenfalls doppelte Tunnelverarbeitung. **Das ändert den Schutzumfang anderer Pi-Programme:** Sie laufen damit nicht automatisch über Proton. Ein bestehender paralleler Client wird weder abgeschaltet noch entfernt. Der Verwaltungsweg bleibt separat; sein eigener Schutz und seine Erreichbarkeit in fremden WLANs müssen geprüft werden.

Dieser Aufbau verwendet weiterhin Proton-Server und die zwingende lokale Netzsperre. Er übernimmt nicht automatisch alle Zusatzfunktionen einer Proton-App. Der WireGuard-Export und dessen Optionen müssen zum gewünschten Proton-Dienst passen. Weder eine zusätzliche App noch zwei hintereinander geschaltete Verbindungen werden hier als eigenständiger Beweis stärkerer Anonymität gewertet. Der tatsächliche Ausfalltest bleibt nötig.

Für eine spätere frische Installation wäre Raspberry Pi OS Lite ohne Desktop passend. Ein vorhandenes OS wird deswegen nicht automatisch neu installiert. Keine zusätzliche Weboberfläche, Browserautomation, Docker-Laufzeit oder Datenbank ist für das Werkzeug nötig. Python plus die bereits vorhandenen kleinen CLI-Werkzeuge bleiben die Basis.

## Bereits lokal umgesetzt in 1.1

| Änderung | Nutzen | Schutzwirkung |
|---|---|---|
| Kurzer Befehl `pigrab` | Ein Befehl für Queue oder Einzel-URL; Benutzerkennung automatisch | Ruft unverändert den kontrollierten Starter über sudo auf; kein Netzwerk- oder Prüfungsbypass |
| Medieninfos mit `json.dump` in die ohnehin nötige private Arbeitsdatei schreiben | Keine zusätzliche vollständige JSON-Zeichenkette zum Schreiben | Gleiche Informationen, gleiche private Datei, gleiche Löschung; keine neuen persistenten Daten |
| Medieninfo-Objekt vor dem echten Transfer freigeben | Großer Format-/URL-Baum bleibt nicht über den gesamten Download/Remux im Python-Hauptprozess | Retry nutzt dieselbe bereits nötige Datei; IP-Prüfung und frische Auflösung je Eintrag bleiben |
| Liveausgabe direkt anzeigen und anschließend verwerfen | Keine zusätzliche aufbewahrte stdout-/stderr-Diagnosekopie | Ausgabe/URL-Entfernung, Heartbeat, Timeout und echte Exit-Codes bleiben erhalten |

Der Starter wird nur bei der späteren Linux-Installation als `/usr/local/bin/pigrab` angelegt. Auf diesem Windows-PC wurde nichts systemweit installiert. Der eigentliche Linux-Netzwerk-/Firewallstarter ist gegenüber 1.0 bytegleich; seine Wirksamkeit ist weiterhin ungetestet.

## Bereits sinnvoll gelöst und beibehalten

- Ein Queue-Eintrag gleichzeitig. Vier HLS-Fragmente innerhalb dieses Downloads sind etwas anderes als vier komplette Videos parallel.
- FFmpeg remuxt mit `-c copy`; keine Video-/Audiokodierung und kein Bedarf an Hardware-Encoder-Einrichtung.
- Roh- und Enddateien bleiben auf demselben Dateisystem. Die endgültige Veröffentlichung benötigt keine weitere vollständige Dateikopie.
- Feste Referenzprogramme und gesperrte Offline-Abhängigkeiten; keine automatisch nachgeladenen Plugins oder JS-Runtimes.
- Metadaten-, Stream- und Anhangsprüfung vor der Veröffentlichung. Die ausgewählten Spuren bleiben erhalten.
- Alle Netzwerkprüfpunkte, DNS-Regeln, Heimatland-/Organisationsregeln, Proben und die Sperre gegen direkten Ausgang bleiben bestehen. Keine Zwischenspeicherung alter IP-Ergebnisse, um Prüfungen zu überspringen.

## Was am Pi gemessen werden sollte

Die großen zu erwartenden Zeitanteile sind WLAN/VPN/Server, verpflichtende externe Prüfungen und Datenträgerzugriffe. Das ist eine Hypothese aus dem Ablauf, keine Messung. Vor einer Änderung jeweils dieselben Medien/gleichen VPN-Exit und identische Schutzprüfungen verwenden.

| Vergleich | Messung | Entscheidung |
|---|---|---|
| Istzustand unter realem 2-GB-Betrieb | RAM-Spitzen **aller** beteiligten Prozesse, Swap-Aktivität, CPU, freier Speicher, Laufzeit | Erst feststellen, ob überhaupt RAM/CPU ein Engpass ist; Python allein zu messen genügt nicht |
| Vier gegen zwei gleichzeitige HLS-Fragmente | Gesamtzeit, Fehler/Retry, RAM, WLAN-Stabilität | Aktuell bleiben wie beauftragt vier aktiv. Weniger Fragmente sind nur ein späterer Vergleich, keine bereits bewiesene Beschleunigung |
| Vorhandene Ablage gegen geeigneten USB-Datenträger | Download-/Remuxdauer und I/O-Auslastung | Erst bei nachgewiesenem Datenträgerengpass wechseln; keine Hardwareanschaffung für einen bloßen Verdacht |
| Quellen mit getrenntem Audio/Video | Anzahl der nötigen Zusammenführungs-/Remuxläufe und Schreibvolumen | Ein späteres Zusammenlegen von Merge und Bereinigung wäre möglich zu untersuchen, braucht aber neue Stream-/Metadatentests |
| Neustart und WLAN-Wechsel | Gesperrter Start ohne Tunnel, Wiederzugang, vollständiger Ausfalltest | Erst danach einen einfachen Boot-Dienst entwerfen; keine automatische Aufweichung für Captive Portals |

Für das Messen keine URLs/Tokens protokollieren. RAM-Zahlen aus synthetischen Windows-Tests wären kein Nachweis für Pi/Linux. Keine feste MB- oder Geschwindigkeitsersparnis wird ohne Zielgerät angegeben.

## Bewusst ausgeschlossene Abkürzungen

Keine Abschaltung von Kill-Switch/Netzsperre, DNS-Prüfung, Probe oder Metadatenprüfung als normale Optimierung. Keine RAM-Disk für ganze Videos auf einem 2-GB-Gerät. Kein automatischer Direktzugang bei Tunnelproblemen. Alte signierte URLs werden nicht über Einträge hinweg wiederverwendet. Größere Parallelität, aggressiveres Vorladen, lang laufende Extraktor-Dienste oder eine direkte Netzwerk-zu-Enddatei-Pipeline werden ohne Messung und erneute Sicherheitsprüfung nicht eingeführt.

## Offizielle Grundlagen

[WireGuard-Namespace-Integration](https://www.wireguard.com/netns/) dokumentiert den einzigen WireGuard-Ausgang für Klartext. [Proton-WireGuard unter Linux](https://protonvpn.com/support/wireguard-linux) beschreibt manuelle Proton-Profile. [Raspberry Pi OS Lite](https://www.raspberrypi.com/documentation/computers/os.html) ist die Edition ohne grafischen Desktop. [FFmpeg Streamcopy](https://ffmpeg.org/ffmpeg.html#Streamcopy) beschreibt Paketkopieren ohne Dekodieren/Enkodieren. [yt-dlp-Optionen](https://github.com/yt-dlp/yt-dlp#download-options) dokumentieren Fragment-Parallelität und Transferoptionen. Aus diesen Quellen und dem aktuellen Programmablauf wurde der obige Aufbau abgeleitet; das ist kein veröffentlichter Benchmark dieses Werkzeugs.
