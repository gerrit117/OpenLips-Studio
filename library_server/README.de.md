# OpenLips-Bibliothek

[English](README.md) | [Deutsch](README.de.md)

Eine private Heimnetz-Bibliothek für Studio, Xbox-Client und WebUI.
Sie ist **nicht die öffentliche Community-Website**.

## Einfacher Docker-Start

Der Container verwendet **Bridge-Netzwerk und einen HTTP-Port**.
Keine Host-IP-Konfiguration, Discovery, FTP, TLS, Anmeldung oder Kopplung.

```sh
docker pull ghcr.io/gerrit117/openlips-library:latest
docker compose up -d
```

Compose in diesem Ordner ausführen. Danach `http://SERVER-IP:8765` öffnen.
Dieselbe Adresse in Studios Remote-Bibliothek oder im Xbox-Client manuell
eingeben. Für einen anderen Host-Port vor dem Start `OPENLIPS_WEB_PORT`
setzen. Der interne Container-Port bleibt 8765.

### Unraid

Die [Vorlage](unraid/OpenLips-Library.xml) verwenden oder einen Container anlegen:

| Einstellung | Wert |
|---|---|
| Name | OpenLips-Library |
| Repository | ghcr.io/gerrit117/openlips-library:latest |
| Netzwerk | Bridge |
| Privilegiert | Nein |
| TCP-Container-Port | 8765 |
| TCP-Host-Port | 8765 |
| Container-Appdata-Pfad | /data |
| Host-Appdata-Pfad | /mnt/user/appdata/openlips-library |
| Container-Bibliothekspfad | /library |
| Host-Bibliothekspfad | /mnt/user/OpenLips-Library |
| Datenzugriff | Lesen/Schreiben |
| Variable PUID | 99 |
| Variable PGID | 100 |
| WebUI | http://[IP]:8765/ |

Zusätzliche Parameter und Post Arguments leer lassen. Alte OPENLIPS_BIND-
Variablen, FTP-Ports und Host-Netzwerk-Einstellungen entfernen.
Keine manuelle Änderung der server.json nötig.
Einen eigenen Appdata-Ordner verwenden, nicht die gesamte Medienfreigabe.

Die Starthilfe bereitet die Besitzrechte von /library und dessen Inhalt
vor und gibt anschließend root-Rechte dauerhaft ab.
Der Server läuft als PUID/PGID, nicht als root.
Eine vorhandene server.json bleibt unverändert und steuert das Netzwerk
nicht mehr. Projekte, Medien, Pakete und Datenbank liegen direkt unter /library,
nicht in Appdata. Dafür eine eigene Unraid-Freigabe auswählen.
Für eine vorhandene Sammlung den Container stoppen und den **Inhalt** von
/mnt/user/appdata/openlips-library/library in die neue Bibliotheksfreigabe
kopieren, einschließlich library.sqlite3 und aller Unterordner.
Das Original behalten, bis die neue Sammlung geprüft wurde.
Die Anwendung verschiebt oder löscht keine alten Dateien automatisch.

Die Vorlage unter
`/boot/config/plugins/dockerMan/templates-user/my-OpenLips-Library.xml`
ablegen und unter Docker > Container hinzufügen auswählen.

## Updates und Sicherungen

### Unraid findet beim Bearbeiten/Updaten keine Konfiguration

Die DockerMan-Vorlage liegt auf dem Unraid-Boot-Stick, **nicht** in `/data`.
Bei einem direkt per Docker/Compose angelegten Container kann diese Vorlage
fehlen. Im Unraid-Terminal den tatsächlichen Container-Namen verwenden:

```sh
curl -fL https://raw.githubusercontent.com/gerrit117/OpenLips-Studio/main/library_server/unraid/recover-template.sh -o /tmp/openlips-recover.sh
bash /tmp/openlips-recover.sh openlips
```

`openlips` durch den Namen aus der Docker-Übersicht ersetzen. Die Hilfe liest
`docker inspect`, übernimmt den Namen, Port, Pfade und Benutzer und erstellt
`/boot/config/plugins/dockerMan/templates-user/my-<Name>.xml`. Eine bestehende
Vorlage wird zuvor gesichert. Container und Songdateien bleiben unverändert.
Danach Docker neu laden, **Bearbeiten** öffnen und **Anwenden**. Unbekannte
Mounts oder alte Netzwerkeinstellungen werden nicht blind ersetzt.
Bleibt die WebUI hängen, Docker-Status und Unraid-Systemprotokoll prüfen;
ein funktionierendes `/api/v1/status` bestätigt nur den Bibliotheksdienst,
nicht den Zustand von Unraids Docker-Verwaltung.

### Studio synchronisieren

Im Studio-Menü **Werkzeuge > Bibliothek > Bibliotheksordner wählen** den
gewünschten Hauptordner festlegen. `workspace` enthält bearbeitbare `.olp`,
`projects` unveränderliche Projektstände, `media` gemeinsame Mediendaten und
`publish` fertige DLCs. Export bei aktivierter Bibliothek verwendet `publish`
direkt statt einer zusätzlichen Exportkopie. Alte Ordner werden nicht gelöscht
oder automatisch verschoben.

In **Remote-Bibliothek** die HTTP-Adresse verbinden und **Bibliothek
synchronisieren** wählen. Projekte einschließlich Cover/Medien sowie fertige
DLCs werden in beide Richtungen ergänzt. **Automatisch synchronisieren**
wiederholt dies im verbundenen Studio alle 60 Sekunden. Es ist kein
Löschabgleich: Änderungen bleiben als Projektversionen erhalten, entfernte
Songs können beim nächsten Abgleich aus der anderen Bibliothek zurückkommen.
Aus dem Dateisystem neu gespeicherte `workspace/*.olp` werden dabei erfasst.
Beliebige lose Dateien in anderen Ordnern werden nicht automatisch importiert.
Community `.ols`-Uploads brauchen weiterhin Anmeldung und Rechtebestätigung;
das Paket enthält keine Audio-/Videodateien. Reine DLCs sind kein Ersatz für
ein bearbeitbares Community-Projekt.

Relevante Änderungen auf main bauen und testen automatisch Linux amd64,
bevor latest veröffentlicht wird. Unveränderliche sha-<vollständiger-Commit>-
Tags erlauben die Rückkehr zu einem früheren Stand.
Für Updates das Image laden und den Container neu erstellen; Datenvolume behalten.
Die Zustandsprüfung nutzt localhost im Container und benötigt keine Zugangsdaten.

Für Sicherungen den Container stoppen und /library sowie /data sichern.
`docker compose down -v` löscht die Sammlung. Lokal bauen:

```sh
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

## Funktionen

- Deutsche/englische WebUI, heller/dunkler Modus, Suche und Metadatenbearbeitung.
- UltraStar TXT, Gesangs-MIDI, LRC, .ols und portable .olp importieren.
- Cover, Audio, Video, Projekte und fertige DLCs/Songpacks aufbewahren.
- Charts/Lyrics konvertieren und native Lips-Daten, MIDI oder LRC exportieren.
- Gemeinsame HTTP-Schnittstelle für Studio und Xbox-Client.

Unter Songs erscheinen auch fertige DLCs und alle Songs eines Songpacks,
ohne dass ein bearbeitbares Projekt vorhanden sein muss. Die Spalte Typ
unterscheidet DLCs, Projekte, Community-Importe, UltraStar, MIDI und LRC.
Bei fertigen DLCs stehen der Originalpaket-Download und der Xbox-Content-Zielordner
in den Details. Bei einem Song aus einem Pack wird das vollständige Pack
heruntergeladen, kein neu erzeugtes Einzel-DLC. Downloads bleibt zusätzlich
als Übersicht aller fertigen Dateien und Exportversionen erhalten.

LRC-Entwürfe benötigen Tonhöhen für bewertbare Charts. Kompatible
Medienkonvertierung benötigt weiterhin Windows und ist im Container nicht aktiv.
USDB, öffentliche Community-Importe und Konsolen-Agent-Transport bleiben inaktiv.
Studios Desktop-Server behält seine separaten optionalen Discovery-/FTP-Funktionen.

## Netzwerk

HTTP ohne Anmeldung: Alle Geräte mit Zugriff dürfen die Bibliothek verwalten.
Nur im vertrauenswürdigen Heimnetz betreiben; keine Portfreigabe ins Internet.
Keine Analyse oder externen Schriftarten. Der Browser speichert nur Sprach-
und Designpräferenzen. Hochgeladene Dateien werden als Daten behandelt,
niemals als Programme ausgeführt.

## Credits

Qt for Python, Mido, Pyphen, Pillow, pyftpdlib, python-zeroconf/ifaddr,
cryptography und Lucide sind in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) aufgeführt.
Nur Material verwenden und teilen, für das die erforderlichen Rechte vorliegen.
OpenLips ist unabhängig von Microsoft, Xbox und den Entwicklern/Publishern von Lips.
