# OpenLips-Bibliothek

[English](README.md) | [Deutsch](README.de.md)

Eine private Bibliothek für das Heimnetz, gemeinsam nutzbar durch Studio,
Xbox-Client und WebUI. Sie ist **nicht die öffentliche Community-Website**.

## Verbinden

Standard ist **HTTP ohne Authentifizierung**. Keine Konten, Passwörter,
Zugangsschlüssel, Zertifikate oder Gerätekopplung. Alle Geräte im erreichbaren
Heimnetz dürfen die Bibliothek nutzen und verwalten.

Studio und Xbox-Client finden Bibliotheken per mDNS
(`_openlips._tcp.local.`). Findet Studio eine offene Bibliothek, verbindet es
sich automatisch; bei mehreren wählst du die gewünschte aus. Falls Router,
VLAN oder VPN Multicast blockieren, bleibt die manuelle Eingabe einer privaten
IP-Adresse möglich.

In Studio die Bibliothek aktivieren und ihren lokalen Server starten, um die
Sammlung freizugeben. Allein durch den Programmstart wird kein Server geöffnet.
Vorbereitete Dateien sind auch über anonymes, schreibgeschütztes FTP verfügbar.
Das Kopieren von Studio zu Aurora ist eine separate Verbindung und verwendet
weiterhin Auroras eigene FTP-Einstellungen.

## Docker

In diesem Ordner starten:

```sh
OPENLIPS_BIND=192.168.1.100 docker compose up -d
```

Die Beispieladresse durch die private IPv4-Adresse des Docker-Hosts ersetzen.
Unter `http://192.168.1.100:8765` öffnet sich die Bibliothek direkt,
ohne Loginseite.

Direkt laden: `docker pull ghcr.io/gerrit117/openlips-library:latest`.
Änderungen auf `main` bauen und testen automatisch Linux amd64, bevor `latest`
veröffentlicht wird. Unveränderliche `sha-<vollständiger-Commit>`-Tags erlauben
die Rückkehr zu einem früheren Stand. Für Updates das neue Image laden und
den Container neu erstellen; die Anwendung startet ihren Host nicht selbst neu.

### Unraid

Die [Unraid-Vorlage](unraid/OpenLips-Library.xml) verwenden oder einen Container
mit Repository `ghcr.io/gerrit117/openlips-library:latest`, Netzwerk **Host**,
Variable `OPENLIPS_BIND` mit Unraids Heimnetz-IPv4 und folgender Zuordnung anlegen:
`/mnt/user/appdata/openlips-library` → `/data`, lesend und schreibend.
Der Ordner muss für UID/GID `10001` beschreibbar sein:

```sh
mkdir -p /mnt/user/appdata/openlips-library
chown 10001:10001 /mnt/user/appdata/openlips-library
```

Die Vorlage unter
`/boot/config/plugins/dockerMan/templates-user/my-OpenLips-Library.xml` ablegen
und unter **Docker > Container hinzufügen** auswählen. Kein privilegierter
Modus, kein TLS. Neue Images über Unraids Update-Funktion übernehmen und
Appdata dabei behalten. Lokal bauen:
`docker compose -f compose.yaml -f compose.build.yaml up -d --build`.

Das Datenvolume bleibt bei Updates erhalten. Unter Linux ermöglicht
Host-Netzwerkbetrieb mDNS und passives FTP. Docker Desktop benötigt die
entsprechende Host-Netzwerk-Unterstützung.
Ports: HTTP TCP `8765`, FTP TCP `2121`, passives FTP TCP `50000–50009`,
mDNS UDP `5353`. Keine Weiterleitung dieser Ports ins Internet einrichten.

Das Image läuft ohne Root-Rechte und ohne Docker-Socket. Nur ausgewählte
Studio-/Toolset-Dateien und lokale UI-Assets werden eingebunden, nicht die
private Community-Website, Originalspiele, Songs oder Geheimnisse.
Für Sicherungen den Server stoppen und das vollständige Bibliotheksvolume
sichern. `docker compose down -v` löscht die gespeicherten Daten.

## Funktionen

- Deutsche/englische WebUI, heller/dunkler Modus und Katalogsuche.
- UltraStar TXT, Gesangs-MIDI, LRC, `.ols` und portable `.olp` importieren.
- Cover, Audio und Video aufbewahren; Metadaten als neuen Stand korrigieren.
- Zeitmarkierte Lyrics zu Noten zuordnen und Lips-Charts/Lyrics, MIDI oder LRC exportieren.
- LRC-Entwürfe benötigen Tonhöhen, bevor daraus bewertbare Charts werden.
- Fertige Studio-DLCs und Songpacks aufbewahren und herunterladen.
- Gemeinsame Schnittstelle für lokales/entferntes Studio und den Xbox-Client.

Plattformunabhängige Medienkonvertierung, nativer Konsolen-Agent-Transport,
USDB-Aufträge und Community-Import sind im Docker-Dienst noch nicht aktiv.
Die vorbereiteten Endpunkte melden `501`. Der bisher geprüfte
Medien-Encoder benötigt Windows; Chart-/Lyrics-Konvertierung funktioniert
davon unabhängig.

Hochgeladene Dateien werden nicht als Programme ausgeführt. Größenlimits,
Pfadprüfung, Hashvergleich und Zwischenablage für unvollständige Übertragungen
bleiben bestehen; dafür braucht es keine Benutzeranmeldung.
Alle erreichbaren Geräte gelten als berechtigt, die Sammlung zu verwalten.
Keine Analyse, externen Schriftarten oder Einbettungen; im Browser werden
nur Sprache und Darstellung gespeichert.

## Entwicklung

```sh
python -m library_server.app --config /absolut/bibliothek/server.json --library /absolut/bibliothek/daten --bind 192.168.1.100
```

Bestehende Konfigurationen wechseln beim normalen Start in den offenen
Heimnetzmodus. Frühere Zertifikate bleiben lokal erhalten, werden aber nicht
mehr verwendet. Der bisherige geschützte Modus lässt sich ausdrücklich mit
`--authenticated` aktivieren; im normalen Heimnetz-Workflow ist das unnötig.

Siehe [API-Dokumentation](../docs/xbox_library_server.de.md) und
den lokalen Xbox-Client. Tests unter Windows ersetzen
keinen echten Docker-/Linux- oder Konsolentest.

## Danksagungen

Qt for Python, Mido, Pyphen, Pillow, pyftpdlib, python-zeroconf/ifaddr,
cryptography und lokal eingebundene Lucide-Icons:
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
Nur Material verwenden/teilen, für das die nötigen Rechte vorliegen.
OpenLips ist unabhängig von Microsoft, Xbox und den Entwicklern/Herausgebern von Lips.
