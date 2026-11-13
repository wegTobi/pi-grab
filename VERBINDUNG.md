# Fehlender Pi-Zugang und wechselnde WLANs

Am 12.11.2026 war vom Windows-PC kein konkreter Pi-Zugang nachweisbar:

- Im damals geprüften Windows-Benutzerprofil existierte kein `.ssh`-Ordner: kein dortiger SSH-Schlüssel, keine benutzerspezifische Konfiguration/known_hosts.
- `C:\ProgramData\ssh` existiert, enthielt bei der Prüfung aber keine nutzbare Clientkonfiguration.
- Windows OpenSSH-Client ist vorhanden.
- `Resolve-DnsName raspberrypi.local -QuickTimeout` und Python `getaddrinfo('raspberrypi.local', 22)` scheiterten: Name nicht auflösbar.
- Netzwerk-Nachbartabelle über CIM war in der Ausführungsumgebung nicht zugänglich; `arp -a` lieferte einen Fehler. Es wurde deshalb weder eine vollständige LAN-Inventur behauptet noch ein unbekanntes Netz gescannt.
- Es gab keine Zieladresse, an der TCP/22 oder eine SSH-Anmeldung seriös hätte geprüft werden können. **Nicht nachgewiesene Erreichbarkeit ist kein Nachweis, dass der Pi ausgeschaltet oder grundsätzlich unerreichbar ist.** Es wurde kein Passwort geraten und kein SSH-Hostschlüssel ungeprüft akzeptiert.

Benötigt werden konkret:

1. Beim ersten Einrichten Zugang zum Pi über Bildschirm/Tastatur oder ein bekanntes gemeinsames privates LAN. Dort `hostname`, `whoami`, `hostname -I`, `systemctl is-active ssh` und die SSH-Hostschlüsselfingerprints ermitteln. Noch ist nicht einmal nachgewiesen, dass SSH aktiviert ist.
2. Die erreichbare Pi-Adresse bzw. der Fernzugriffsname, SSH-Benutzer und SSH-Port. Ein verifizierter Hostschlüsselfingerprint verhindert eine Anmeldung am falschen Gerät.
3. Ein auf dem Pi eingerichteter öffentlicher PC-Schlüssel oder eine dort lokal eingerichtete Anmeldung. Der **private** Schlüssel und Passwörter bleiben lokal; keine Übertragung in diesen Chat nötig. Ein anderer bereits vorhandener Schlüsselpfad müsste genannt werden, falls nicht das Standardprofil verwendet wird.
4. Die Ausgabe von `inventory.py` bzw. die entsprechenden Geräteangaben: Modell/RAM, OS, Architektur, Speicher, geplante Ablage und konkreter Proton-Betriebsmodus. Proton auf dem PC belegt keinen Tunnel auf dem Pi.
5. Für den Downloadbereich ein eigener Proton-WireGuard-Export und eine dafür verfügbare Verbindung. Schlüssel ausschließlich auf dem Pi verwenden. Keine dauerhafte Freigabe der Heimatland-/Organisationsregeln zum Erzwingen von Downloads.

Öffentliche WLANs ändern lokale IP-Adressen und können direkte Gerätekommunikation sperren. Ein Name mit `.local` funktioniert üblicherweise nur im jeweiligen lokalen Netz. Eine Proton-Clientverbindung allein stellt keinen allgemeinen eingehenden SSH-Fernzugang bereit. Eine dauerhafte Erreichbarkeit braucht einen separat eingerichteten privaten Fernzugriffsweg oder einen eigenen erreichbaren SSH-Zwischenserver. Diese Entscheidung, Identität und Anmeldung sind noch offen. Eine gegebenenfalls vorhandene Proton-Portweiterleitung wird nicht ungeprüft als stabiler SSH-Zugang verwendet.

Der Downloader verlangt keinen solchen Verwaltungsweg im Download-Namespace. Verwaltung, WLAN-Anmeldung und paralleles Proton bleiben im Host. Die Namespace-Einrichtung verändert keine Host-Routen und legt keine SSH-Firewallregeln an. Damit wird der vorhandene Zugang durch diese Einrichtung nicht absichtlich umgeleitet. Ob der parallele Proton-Kill-Switch einen separaten Verwaltungsweg blockiert, muss vor Ort geprüft werden.

Bei Captive Portals zuerst im Host anmelden. Blockiert das WLAN WireGuard-UDP oder läuft die Anmeldung ab, muss der Downloader gesperrt bleiben. Es gibt keinen direkten WLAN-Fallback. Keine automatische VPN-Unterbrechung zur Portal-Anmeldung. Bei häufigen Wechseln zuerst das Host-Netz stabilisieren, danach neue Queue/URLs beginnen; signierte Links können beim Wechsel verfallen.
