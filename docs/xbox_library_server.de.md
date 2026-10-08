# Xbox-Übertragung, Bibliothek Und Lokaler Helfer

[English](xbox_library_server.md) | [Deutsch](xbox_library_server.de.md)

Alle drei Funktionen sind optional. Studio öffnet beim Start keine Netzwerkports,
ändert keine Firewallregeln und installiert keinen Hintergrunddienst.

## Auf Xbox Kopieren

Die Funktion steht unter **Werkzeuge > Auf Xbox kopieren** und nach einem
DLC-/Songpack-Export bereit. Xbox-IP, Aurora-FTP-Port, Benutzername, Passwort
und Content-Ordner eintragen, normalerweise `Hdd1/Content`. Die Verbindung
lässt sich vor der Übertragung testen.

Studio bestimmt den Unterordner automatisch:

```text
Hdd1/Content/0000000000000000/4D530888/00000002/<Paketdateiname>
```

Das vollständige Paket wird geprüft, zunächst außerhalb von `00000002`
hochgeladen, wieder eingelesen und per SHA-256 verglichen. Erst danach wird es
an seinen endgültigen Ort verschoben. Vorhandene Pakete werden nicht ersetzt.
Bei einem Abbruch wird kein unvollständiges DLC installiert. Ein verlorener
Netzwerkzugang kann eine temporäre Datei im Ordner `.openlips-transfer`
hinterlassen; dieser liegt außerhalb des vom Spiel gelesenen DLC-Unterordners.
Die PC-Kopie bleibt erhalten. Unterstützt werden derzeit die von Studio
erstellten unsignierten Lips-LIVE-Pakete mit einfachen Hashtabellen, nicht
beliebige Xbox-Dateien.

Gespeichert werden nur Verbindungseinstellungen ohne Passwort. Das Passwort
bleibt im Arbeitsspeicher. Normales FTP, also auch Auroras üblicher FTP-Zugang,
ist unverschlüsselt. Nur im vertrauenswürdigen Heimnetz oder VPN verwenden;
keine FTP-, XBDM- oder API-Portweiterleitung ins Internet einrichten. Optionales
FTPS prüft Zertifikate und umgeht keine Zertifikatsfehler. Ob das Spiel einen
Song tatsächlich abspielt, muss weiterhin auf der Konsole getestet werden.

## Zuschaltbare Bibliothek

Unter **Werkzeuge > Lokale Bibliothek aktivieren** einschalten. Der erste
lokale Speicherort liegt im Benutzerdatenordner; **Bibliotheksordner wählen**
ändert ihn später, ohne den bisherigen Ordner zu löschen. Im Reiter zwischen
lokaler und Remote-Bibliothek wechseln. In der lokalen Bibliothek
kannst du den aktuellen Song sichern, `.olp`-Projekte oder fertige Studio-DLCs
hinzufügen, suchen, Projekte wieder öffnen, ausgewählte Songs exportieren und
vorhandene Pakete auf die Xbox kopieren.

Bei aktivierter Bibliothek werden erfolgreiche DLC-Exporte zusätzlich mit
ihren Projekten und Audio-, Video- und Coverdateien gesichert. Originaldateien
werden weder verschoben noch gelöscht. Gleiche Projektinhalte werden nicht
doppelt erfasst; Änderungen an Noten, Metadaten oder Medien ergeben einen
weiteren Stand. Das Öffnen eines gesicherten Stands überschreibt diesen nicht.
Paket- und Songinformationen kommen aus dem STFS-Header und der `DLC.xml`,
einschließlich aller Songs eines Packs, nicht aus dessen Hex-Dateinamen.

Das Deaktivieren blendet die Bibliothek aus, **löscht aber keine Dateien**.
Sie ist lokal, kein Community-Upload und kein Cloud-Backup. Für Quelldateien
und fertige DLCs wird entsprechend Speicherplatz benötigt. Für eine Sicherung
Studio und Helfer stoppen und den ganzen Bibliotheksordner kopieren. Nur
`publish/` enthält zum Abruf freigegebene DLCs; Quelldateien, Projekte,
SQLite-Datenbank und Zugangsdaten liegen außerhalb dieses Ordners.

## Headless-Betrieb

**Lokaler Server** gibt die Sammlung im Heimnetz frei. Studio wählt dafür
standardmäßig eine private IPv4-Adresse und meldet die Bibliothek per mDNS an.
Normaler Betrieb: **HTTP ohne Authentifizierung**, keine API-Schlüssel,
FTP-Passwörter, Zertifikate oder Kopplungscodes. Unter **Verbindungsdaten**
stehen nur die Adressen.

Ohne Editor:

```powershell
OpenLipsStudio.exe --server --config "D:\OpenLipsLibrary\server.json"
```

Quellcode: `python -m studio --server --config PFAD`.
Ersteinrichtung: `python -m studio --server-init --config PFAD --library ORDNER --bind PRIVATE_IPV4`.
Bestehende Konfigurationen wechseln beim normalen Start in den offenen
Heimnetzmodus. Frühere Zertifikate bleiben lokal erhalten, werden jedoch
nicht verwendet. Der alte geschützte Modus ist nur mit `--authenticated`
aktiv; für den Heimnetz-Workflow wird er nicht benötigt.

Die Geräte benötigen untereinander Zugriff auf API TCP `8765`, FTP TCP
`2121`, passives FTP TCP `50000-50009` und mDNS UDP `5353`. Keine
automatischen Firewalländerungen oder Internet-Portweiterleitungen.
Jedes erreichbare Gerät darf die Bibliothek verwalten. Bei blockiertem
Multicast bleibt die manuelle Eingabe der privaten IP-Adresse möglich.
Vorbereitete Dateien lassen sich anonym und schreibgeschützt per FTP abrufen;
sie bleiben nach dem Download gespeichert.

Dauerbetrieb ist unter einem normalen Benutzer mit Windows-Aufgabenplanung
möglich. Encoding im Windows-Systemdienst unter Session 0 wurde nicht geprüft;
ein solcher Dienst wird nicht installiert.

## Schnittstelle Und Grenzen

Der [englische API-Vertrag](xbox_library_server.md#client-api-version-1) beschreibt
Katalog, Importe, Medien, Aufträge und fertige Ausgaben. Im normalen
Heimnetzmodus ist kein `Authorization`-Header nötig; `/identity` meldet
`auth_required: false`. Die WebUI öffnet direkt die Bibliothek.
Kopplungscodes und Geräte-Tokens gehören nur zum optionalen alten
Authentifizierungsmodus. Es gibt keine Anmeldung per Cookie oder URL-Parameter.
Browseranfragen bleiben auf denselben Ursprung beschränkt.

Aufträge verwenden ausschließlich bekannte Bibliotheks-IDs, keine beliebigen
Dateipfade, Programme oder Download-URLs. Ein Song oder ein benanntes Pack mit
2–16 Songs kann gebaut werden. Builds laufen nacheinander; höchstens acht
Aufträge sind gleichzeitig offen. Passende frühere Worker-Builds werden wieder
verwendet. Nach einem Neustart gelten unterbrochene Aufträge als fehlgeschlagen.

Mit `kind` lassen sich außerdem einzelne Projekte als `.ols` (`chart`), MIDI
(`midi`) oder Enhanced LRC (`lrc`) exportieren. `.ols` enthält native Lips-Charts,
Lyrics und Cover, aber kein Audio/Video. Diese Aufträge benötigen keinen
Windows-Encoder. Unvertonten LRC-Entwürfen zuerst in Studio Tonhöhen zuweisen.
Die Ergebnis-ID steht ebenfalls in `package_id`; solche Dateien stehen im
Katalog unter `artifacts` statt `packages`.

Für den [nativen Xbox-Client](../xbox_client/README.de.md) gibt es einen lokalen
Entwicklungsbuild; der Test auf echter Hardware steht noch aus. Der Abgleich
bereits installierter Songs und USDB-Aufträge über die Server-API fehlen noch.
Die [Docker-WebUI und anonyme Remote-Bibliothek](../library_server/README.de.md)
sind vorbereitet. Vorhandene USDB-/Downloadfunktionen in Studio bleiben
unverändert. Unter Linux/macOS funktionieren Bibliothek,
fertige Pakete und Chart-/Lyrics-Konvertierung. Neue kompatible Videos benötigen
weiterhin Windows. Der Docker-Dienst deaktiviert daher neue DLC-Erstellung,
nicht aber Importe und Chart-/Lyrics-Exporte.
