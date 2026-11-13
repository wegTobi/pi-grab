# Recherche: robuste Pi-Downloads über öffentliche WLANs

Stand: 12.11.2026. Diese Recherche dient als Architektur-Inspiration. GitHub-Projekte sind keine Sicherheitszertifizierung; Reddit-Beiträge sind Einzelberichte. Es wurden keine fremden Skripte ausgeführt oder übernommen.

## Vergleich und Übertragbarkeit

| Beispiel | Nützliche Idee | Grenze für PiGrab |
|---|---|---|
| [Ketch](https://github.com/linroid/Ketch) | Dauerhafte Queue, unvollständige Dateien bleiben als temporäre Dateien erkennbar; Resume wird nur fortgesetzt, wenn der Server die Datei als unverändert bestätigt. | Allgemeiner Download-Manager. Ein Video-Resolver kann kurzlebige signierte Medienlinks bekommen; ein gespeicherter Direktlink ist dann kein sicherer Resume-Schlüssel. |
| [systemd: NETWORK_ONLINE](https://github.com/systemd/systemd/blob/main/docs/NETWORK_ONLINE.md) | `network-online.target` ist nur ein Startzeitpunkt, keine laufende Verfügbarkeitsgarantie. Anwendungen müssen Netzausfälle selbst überstehen. | Daher nicht lediglich einen Dienst einmal nach `network-online.target` starten und danach dauerhaft laufen lassen. |
| [Vanished/VPNBOX](https://github.com/Vanished/VPNBOX) | Einfaches Sicherheitsziel: Internetverkehr nur über den VPN-Pfad zulassen. | Das alte Pi-Setup verwaltet systemweite Firewall-/Routingregeln. Diese Regeln nicht ungeprüft übernehmen; Proton Advanced Kill Switch soll alleiniger VPN-/Kill-Switch-Eigentümer bleiben. |
| [ProtonVPN Docker WireGuard](https://github.com/tprasadtp/protonvpn-docker) | ARM64-Unterstützung und ein gemeinsamer VPN-Netzwerkbereich für abhängige Prozesse sind ein mögliches Muster. | Das Projekt bezeichnet seinen Kill Switch als experimentell und als nicht vollständige Sperre für lokale/Link-Local-Netze. Es würde außerdem eine zweite, manuelle Proton-WireGuard-Integration neben der gewünschten Proton-App bedeuten. |
| [r/ProtonVPN: Headless-Pi-Erfahrungen](https://www.reddit.com/r/ProtonVPN/comments/1qz6o2s/is_support_for_raspberry_pi_coming_or_not/) | Nutzer berichten, dass die Proton-CLI auf headless Setups Probleme macht und verwenden stattdessen manuelle WireGuard-Konfigurationen. | Anonyme Community-Berichte; weder offizielle Kompatibilitätszusage noch Nachweis, dass der aktuelle GUI-Client auf diesem Pi zuverlässig mit Advanced Kill Switch läuft. |
| [r/ProtonVPN: Pi-WireGuard-Abbruch](https://www.reddit.com/r/ProtonVPN/comments/1xg0z6i/wireguard_on_raspberry_pi_drops_connection_when/) | Reale Pi-Nutzer berichten von Abbrüchen unter hoher Downloadlast. Das unterstreicht, Abbruch/Wiederverbindung praktisch zu testen. | Einzelfall und Torrent-Last; keine belastbare Aussage über einen normalen HTTPS-Videoabruf oder Ursache. |

## Was wir daraus für die gewünschte Lösung verbessern

1. **Nur ein VPN-Eigentümer.** Die Zielarchitektur nutzt die offizielle Proton-App samt Advanced Kill Switch, keine parallele `wg-quick`-Verbindung und keine zweite Proton-Implementierung. Der vorhandene PiGrab-Netzwerk-Namespace ist für diese gewünschte Betriebsart erst nach Umbau geeignet.
2. **Geschlossene Freigabe vor jeder Netzwerkaktion.** Die Queue darf selbst bei Boot, Captive Portal, DNS-Ausfall, VPN-Neuverbindung oder unbekanntem Status nur lokal warten. Vor Video-/Probe-/Resolver-Anfragen wird ein positiver VPN- und Egress-Nachweis verlangt. Ist die Proton-App auf der Geräteplattform nicht zuverlässig erkennbar, wird nicht heruntergeladen.
3. **Queue dauerhaft, aber sparsam.** SQLite aus der Python-Standardbibliothek genügt für Link, Name, Status, Zeiten und Fehlerklasse. Eine einzelne aktive Aufgabe (Concurrency 1) hält RAM, CPU, Verbindungen und thermische Last niedrig. Geheimnisse oder signierte Medien-URLs kommen nicht in die Queue.
4. **Resume anhand von Identität, nicht blindem Dateianhang.** Bei einer gewöhnlichen Direktdatei nur fortsetzen, wenn Range-Unterstützung und ein stabiler ETag/Last-Modified-Wert die Identität belegen. Nach WLAN-/Exit-Wechsel wird bei Video-Extractor-Links der ursprüngliche Seitenlink neu aufgelöst. Unbekannte Identität bedeutet nur den aktuellen Eintrag neu starten; fertige Dateien bleiben unberührt.
5. **Atomare Fertigstellung.** In private Arbeitsdateien laden, Container-/Metadatenprüfungen durchführen und erst danach im selben Dateisystem atomar veröffentlichen. Bei Stromverlust bleibt eine temporäre Datei sichtbar/unfertig und wird nicht als Erfolg gezählt.
6. **WLAN-Recovery ohne Portal-Umgehung.** WLAN/Captive-Portal manuell im Host anmelden; Advanced Kill Switch bleibt aktiv. `network-online.target` allein reicht nicht als Erkennung. Ein schlanker Queue-Dienst kann nach Fehler mit begrenztem Backoff erneut prüfen; der Nutzer kann den Pi aber auch ganz abschalten, weil die Queue lokal gespeichert bleibt.
7. **Lecktests zuerst lokal und kontrolliert.** Auf dem Pi getrennt prüfen: Boot ohne WLAN, WLAN ohne Proton, Proton-Verbindungsabbruch während eines eigenen Testabrufs, Wechsel des WLANs und Neustart. Auf der physischen Schnittstelle darf kein Klartext-DNS oder Video-Zielverkehr erscheinen. Testzugang/physischer Zugriff bereithalten, bevor Netzwerkregeln geprüft werden.

## Was eine VPN-Verbindung nicht löst

Ein Proton-Tunnel verbirgt nicht die Anmeldedaten, Cookies oder identifizierenden Parameter eines Links vor der Zielseite; er verhindert auch keine Zuordnung über Konten, Gerätezugriff oder Zeit-/Volumenmuster. Die [EFF weist darauf hin, dass ein VPN keine Anonymität garantiert](https://ssd.eff.org/ps/module/vpn). Der Pi sollte daher keine persönlichen Browserprofile oder unnötigen Dienste führen; Dateisystemverschlüsselung schützt ausgeschaltete/abhandengekommene Hardware, nicht einen laufenden entsperrten Pi. Diese Maßnahmen reduzieren Risiken, versprechen aber keine Unsichtbarkeit gegenüber jedem Beobachter.

## Status

Diese Punkte sind Ziel-/Prüfkriterien, keine Behauptung, dass sie schon im Code umgesetzt sind. Aktuell fehlen weiterhin Proton-App-Erkennung/Integration und dauerhafte Queue. Der konkrete Pi, seine Proton-Kompatibilität und Kill-Switch-Regeln sind nicht erreichbar bzw. nicht getestet. Siehe auch `Installationsplan-Proton-und-WLAN-Wechsel.md`.

## Erweiterte Stichprobe vom 12.11.2026

Zusätzlich geprüft wurden acht weitere technische Projekte/Quellen und mehrere Reddit-Erfahrungsberichte. Die folgende Tabelle unterscheidet bewusst zwischen belegten Produkteigenschaften und einzelnen Nutzererfahrungen.

| Quelle/Projekt | Tatsächlich interessantes Muster | Übernahme für dieses Projekt? |
|---|---|---|
| [aria2](https://github.com/aria2/aria2) | Speichert offene Aufträge regelmäßig in einer Sitzungsdatei; begrenzt parallele Downloads und kann unvollständige Einträge behalten. | Ja: periodisch und atomar Queue-Zustand sichern. Nein: aria2 nicht zusätzlich einführen, weil PiGrab bereits einen Video-Resolver und yt-dlp-Pfad hat. |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | `.part`-Dateien und Fortsetzen sind Standard. | Ja: Teilstände niemals als fertige Videos veröffentlichen. Resume nur nach einer Identitätsprüfung; bei neu aufgelösten, signierten Medienadressen reicht ein vorhandenes `.part` allein nicht. |
| [Open Download Manager](https://github.com/fossgap/open-download-manager) | SQLite-Historie, Queue, Wiederanlauf und mehrere Engines. | Ja: das Zustandsmodell. Nein: GTK, Java, mehrere Engines und Web-/Clipboard-Automatik wären auf dem 2-GB-Pi unnötige zusätzliche Angriffs- und Wartungsfläche. |
| [gosh-dl](https://github.com/goshitsarch-eng/gosh-dl-cli) | Eine SQLite-Queue bleibt über Neustarts erhalten; nur ein Prozess besitzt einen Speicherort. | Ja: SQLite und ein exklusiver Prozess-Lock. |
| [Burst Download](https://github.com/ErnestAgel/burst-download) | Mehrere HTTP-Bereiche beschleunigen große, stabile Direktdateien; fehlende Range-Unterstützung führt zurück auf eine Verbindung. | Teilweise: höchstens für stabile, bestätigte Direktdateien. Für öffentliche WLANs und kurzlebige Video-URLs sind ein Download gleichzeitig und wenige Verbindungen robuster und diskreter. |
| [ProtonVPN Docker](https://github.com/tprasadtp/protonvpn-docker) | Anwendungscontainer teilen ausschließlich den VPN-Netzbereich; Healthchecks prüfen die Verbindung. | Das „Freigabe erst nach Healthcheck“-Prinzip wird übernommen. Docker und dessen eigener experimenteller Kill Switch nicht: das wäre ein zweiter Proton-Client neben der gewünschten offiziellen App. |
| [NetworkManager](https://github.com/NetworkManager/NetworkManager) / [Raspberry-Pi-Dokumentation](https://www.raspberrypi.com/documentation/computers/configuration.html) | Raspberry Pi OS Bookworm nutzt NetworkManager; bekannte WLANs können automatisch verbunden werden. | Ja: WLAN-Verwaltung dem Betriebssystem überlassen. Der Downloader beobachtet nur den Zustand und verändert keine WLAN-Profile oder Routen. |
| [Raspberry Pi Secure Boot Provisioner](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html) | Kombination aus Secure Boot und LUKS kann Daten auf verlorenem/entwendetem Speicher schützen. | Optional, aber sinnvoll bei körperlichem Verlust des Pi. Es erfordert einen Neuaufbau des Speichers und ist kein Update für die bestehende Installation. |

### Community-Erfahrungen: Einordnung statt Übernahme

- Mehrere Proton-/Pi-Berichte beschreiben, dass die offizielle Linux-CLI auf headless Systemen eingeschränkt oder ungeeignet ist. Andere wechseln deshalb zu manuellem WireGuard. Das ist für deine App-Pflicht gerade **kein** Ersatz.
- Es gibt Berichte über Wi-Fi-/VPN-Abbrüche unter Pi-Last sowie darüber, dass Kill-Switch- oder NetworkManager-Zustände nach Änderungen schwer wiederherzustellen sind. Daraus folgt: keine automatischen Reparaturbefehle, die globale Proton- oder Netzregeln löschen; jede Wiederanbindung wird geschlossen geprüft.
- Nutzer empfehlen oft unbegrenzte WLAN-Wiederholungen oder das Ausschalten des WLAN-Energiesparens. Das kann die Verfügbarkeit verbessern, ist aber keine Sicherheitsmaßnahme und muss auf dem tatsächlichen Pi nach Akku-/Temperatur-/Stabilitätstests entschieden werden.

## Vergleich der möglichen Architekturen

| Architektur | Leckschutz | Pi-Last | Konflikt mit Proton-App | Eignung |
|---|---:|---:|---:|---|
| Offizielle Proton-App + Advanced Kill Switch + schlanker PiGrab-Worker | Vom Proton-Kill-Switch abhängig, mit zusätzlicher positiver VPN-Prüfung vor jedem Auftrag | niedrig | keiner, wenn PiGrab die App nicht verändert | **Zielarchitektur** |
| Eigener WireGuard-Namespace aus der bisherigen PiGrab-Vorbereitung | Stark isolierter Downloader, aber getrennt von Proton-App | niedrig | hoch: zweiter Tunnel/DNS-/Routing-Eigentümer | nur falls die Proton-App auf dem Pi nicht nutzbar ist und du eine neue Entscheidung triffst |
| Docker-/Gluetun-Stack | Containerabhängig; oft brauchbar, aber die Schutzregeln gehören dem Stack | mittel bis hoch | hoch: typischerweise eigener Proton-WireGuard-Client | für Server-Stacks, nicht für die geforderte Proton-App |
| Vollwertiger Download-Manager mit GUI/Weboberfläche | Sehr unterschiedlich | mittel bis hoch | indirekt | zu komplex für einen mobilen 2-GB-Pi |

## Konkret verbesserte Zielanforderungen

1. SQLite im privaten Arbeitsordner, mit WAL-Modus, einer exklusiven Prozesssperre und einer Transaktion pro Zustandswechsel. Die Queue speichert ausschließlich Originalseitenlink, Anzeigename, Zeitpunkte, Fehlerklasse und lokale Arbeitsdatei; keine Login-Daten, Cookies oder signierten Medien-URLs.
2. Aufträge haben klare Zustände: `wartend`, `prüfe_vpn`, `lade`, `unterbrochen`, `fertig`, `fehlgeschlagen`. Nach Boot, WLAN-Wechsel oder VPN-Unterbrechung wird ein aktiver Auftrag immer als `unterbrochen` markiert und erst nach neuer Prüfung fortgesetzt.
3. Eine kleine, explizite VPN-Prüfung validiert mindestens: aktive Proton-Verbindung, erwartete öffentliche Exit-IP, funktionierende Namensauflösung im aktiven VPN-Pfad und keine Änderung dieser IP während der Vorbereitung. Jeder unklare Wert blockiert die Queue.
4. Ein Dienst darf beim Boot starten, aber nie „Internet ist da“ mit „VPN ist sicher“ verwechseln. `network-online.target` ist nur eine Startreihenfolge; die laufende Prüfung bleibt Teil des Workers.
5. Kein Web-UI, keine offene Netzwerk-Schnittstelle, kein Fernzugriffsdienst als Voraussetzung für Downloads. Das vermeidet zusätzliche Ports, Konten und Hintergrundprozesse.
6. Der Downloader läuft als eigener unprivilegierter Benutzer. Nur die Proton-App/NetworkManager verwalten das Netzwerk. Keine Skripte mit pauschalem Firewall-Flush, keine automatische Deinstallation oder Reparatur von Proton-Komponenten.
7. Für Ausschalten: sauber beenden, wenn möglich. Nach einem harten Stromverlust erkennt die Datenbank den unvollständigen Auftrag anhand einer Startmarke und behandelt ihn als unterbrochen; die temporäre Datei wird geprüft statt blind weiterverwendet.
8. Die Datenschutzpriorität bleibt vor Tempo: ein aktiver Auftrag, konservative Wiederholungen und keine automatische Übernahme von Browser-Cookies. Das passt bequem in 2 GB RAM und vermeidet unnötige parallele Fingerprints/Verbindungen.
