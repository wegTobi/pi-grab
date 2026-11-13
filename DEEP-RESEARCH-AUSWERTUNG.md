# Auswertung des eingereichten Deep-Research-Berichts

Stand: 12.11.2026. Dieser Text bewertet den vom Nutzer bereitgestellten Bericht gegen die offizielle Proton-/Raspberry-Pi-Dokumentation und die bisherige lokale Portierung. Er ist keine Behauptung, dass die genannten Projekte auf dem konkreten Pi getestet wurden.

## Ergebnis

Der Bericht liefert gute Muster für eine dauerhafte Queue, temporäre Dateien und echte Ausfalltests. Seine vorgeschlagene Zielarchitektur Docker/Gluetun ist jedoch für die festgelegte Vorgabe ungeeignet: Sie verwendet einen **manuellen Proton-WireGuard-Client in Docker** statt der gewünschten offiziellen Proton-App mit Advanced Kill Switch. Damit entstehen zwei konkurrierende Möglichkeiten:

- Proton-App + Advanced Kill Switch: entspricht der Vorgabe, aber die Kompatibilität auf dem konkreten ARM-/Pi-System muss erst bewiesen werden.
- Gluetun + manuelle Proton-Konfiguration: kann eine brauchbare, getrennte Alternative sein, erfüllt aber die App-Vorgabe nicht und ist kein „Upgrade“ der App-Variante.

Diese beiden Modelle dürfen nicht parallel auf demselben Pi eingerichtet werden. Sie besitzen Routing, DNS, Firewall und Tunnel jeweils selbst und können sich gegenseitig sperren oder doppelt tunneln.

## Korrekturen und belastbare Erkenntnisse

| Aussage im Bericht | Bewertung | Konsequenz |
|---|---|---|
| Raspberry Pi OS/Raspbian wird von Proton nicht offiziell unterstützt. | Belegt. Proton unterstützt offiziell aktuelle Debian-/Ubuntu-Versionen mit GNOME; Raspbian wird ausdrücklich ausgenommen. | Vor einer Installation System, Architektur und Proton-Paketverfügbarkeit prüfen. Keine Kompatibilitätszusage aus einem vorhandenen ARM64-Repository ableiten. |
| Die aktuelle Proton-CLI eignet sich für einen headless Pi. | Nicht belastbar. Proton weist darauf hin, dass die Linux-CLI auf headless Setups nicht funktioniert. | Kein Architekturentwurf darf die CLI als verlässliche headless Voraussetzung behandeln. |
| Advanced Kill Switch ist als Linux-Schutz verfügbar. | Belegt für die Linux-GUI. Proton beschreibt, dass er Verbindungen außerhalb eines aktiven Proton-Tunnels blockiert und Neustarts überdauert. | Erst am Zielgerät prüfen, ob gerade die Linux-GUI auf dessen Architektur läuft und die Einstellung dort tatsächlich verfügbar bleibt. |
| Docker/Gluetun sei die empfohlene Zielarchitektur. | Für einen getrennten manuellen WireGuard-Betrieb plausibel; für die gewünschte Proton-App falsch. | Verwerfen, solange die App-Pflicht gilt. Docker ist auch auf 2 GB RAM möglich, erhöht aber Betrieb, Updates, Logs und Fehlersuche. |
| Eine Firewall-Regel auf dem Host wie `INPUT -i wg0 ACCEPT; INPUT DROP` sei zusätzliche Absicherung. | Ungeeignet als allgemeine Empfehlung. Sie steuert eingehenden Verkehr, verhindert keinen ausgehenden Leak und kann Verwaltung/WLAN-/VPN-Betrieb beschädigen. | Keine globalen Hostregeln aus Blog-/Community-Snippets übernehmen. Der jeweils verantwortliche VPN-Client soll seine Regeln verwalten; dies wird nur mit einem kontrollierten Test überprüft. |
| Externer DNS wie Cloudflare sei eine allgemeine Lösung gegen DNS-Leaks. | Zu grob. Entscheidend ist der tatsächliche Resolver- und Routingpfad; ein fremder DNS-Server kann die Privatsphäreannahmen sogar verändern. | Den von der geprüften Proton-Verbindung vorgesehenen DNS-Pfad verwenden und mit Paketmitschnitt testen, statt DNS nur anhand eines Namens festzulegen. |
| Alle Lösungen seien ARM64-tauglich. | Nicht belegt. ARM64-Fähigkeit eines Containers oder einer Komponente belegt keine vollständige Pi-/Proton-/Kill-Switch-Kompatibilität. | Jede Komponente auf Paketarchitektur, Kernel, NetworkManager und tatsächlichen Start/Neustart testen. |
| Teilstände können nach Neustart fortgesetzt werden. | Als allgemeines Downloadmuster richtig, bei Video-/Extractor-URLs eingeschränkt. | Nur stabile Direktdateien mit Range-Unterstützung und bestätigter Objektidentität fortsetzen. Bei signierten/kurzlebigen URLs von der Originalseite frisch auflösen. |

## Aus dem Bericht übernommene Verbesserungen

1. Die Queue erhält SQLite mit klaren Zuständen und einer exklusiven Prozesssperre. Ein einzelner Worker genügt für den Pi 4 mit 2 GB RAM.
2. Ein Übergang zu `fertig` erfolgt erst nach Abschluss, Remux und Metadatenprüfung. Arbeitsdateien bleiben privat und eindeutig unvollständig.
3. Ausfalltests werden zu einer festen Abnahmeliste: VPN-Ausfall während Abruf, WLAN-Wechsel, Boot ohne WLAN, VPN-Neuverbindung, reguläres Herunterfahren und kontrollierter Stromverlust.
4. PiGrab prüft nicht nur einen Prozessnamen oder ein Interface. Er muss einen plausiblen VPN-Zustand und den tatsächlichen Egress bestätigen; eine Unsicherheit blockiert den Auftrag.
5. Kein Web-UI, keine offene Listener-Schnittstelle und keine dauerhafte Browser-Sitzung sind für den beschriebenen Ablauf erforderlich.

## Zielarchitektur nach der Prüfung

```text
WLAN / Captive Portal (manuell in NetworkManager)
                 │
        offizielle Proton-App
        Advanced Kill Switch
                 │
    PiGrab-Worker als eigener Benutzer
    SQLite-Queue · 1 aktiver Auftrag · private Arbeitsdateien
                 │
       atomar geprüfte fertige Videos
```

Der Worker verändert keine VPN-, DNS-, WLAN- oder Host-Firewallregeln. Er wartet auf einen nachgewiesenen geschützten Pfad. Bei Verlust dieses Nachweises bleibt die Queue lokal stehen.

Falls die offizielle App auf dem tatsächlichen Pi nicht zuverlässig läuft, ist ein Wechsel zu manuellem WireGuard oder Gluetun eine neue Architekturentscheidung, die die App-Vorgabe ersetzt. Sie wird nicht parallel ergänzt.

## Quellen zum Abgleich

- [Proton: Installation auf Debian und Ubuntu](https://protonvpn.com/support/linux-vpn-debian-ubuntu)
- [Proton: Advanced Kill Switch](https://protonvpn.com/support/advanced-kill-switch)
- [Proton: Linux-Übersicht einschließlich Einschränkungen](https://protonvpn.com/support/linux-vpn-setup)
- [Raspberry Pi: Netzwerk-Konfiguration mit NetworkManager](https://www.raspberrypi.com/documentation/computers/configuration.html)
- [yt-dlp: Teilstände fortsetzen](https://github.com/yt-dlp/yt-dlp)
- [aria2: periodisch gespeicherte unvollständige Aufträge](https://github.com/aria2/aria2)
