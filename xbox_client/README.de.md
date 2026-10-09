# OpenLips-Xbox-Client

[English](README.md) | [Deutsch](README.de.md)

Nativer Xbox-360-Bibliotheksclient im OpenLips-Stil. Der lokale Entwicklungsbuild
verwendet das bereits installierte offizielle SDK. Microsoft-Header,
Beispielprogramme und SDK-Werkzeuge werden nicht in dieser Repo verteilt.

## Im Heimnetz

- Offene Bibliotheken automatisch per mDNS finden oder private IPv4-Adresse eingeben.
- HTTP ohne Konten, Passwörter, TLS oder Gerätekopplung.
- Songs durchsuchen, Cover anzeigen und Build-Aufträge auf dem Server verfolgen.
- Fertige DLCs laden, Größe/SHA-256 prüfen und Kopien im Cache behalten.
- Optional vollständige Pakete in einen gewählten Xbox-Content-Ordner kopieren.
  Unvollständige Übertragungen werden separat abgelegt; vorhandene Dateien bleiben erhalten.
- Deutsch/Englisch, heller/dunkler Modus und eigene Bildschirmtastatur zur Suche.

Medienkonvertierung bleibt Aufgabe des Windows-Helfers. Die Xbox ist kein
Encoder. Der Abgleich bereits installierter Songs, ein eigener FTP-Server auf
der Konsole und direkte USDB-/Community-Abfragen sind noch nicht umgesetzt.

## Lokal Bauen

`tools/build_xbox_client.py` verwendet unseren Quellcode, das installierte SDK
und festgelegte Versionen der Open-Source-Abhängigkeiten. Generierte Dateien
gehören in ignorierte `private/`-Ordner. Eine verwendbare Schrift bereitstellen;
der lokal erzeugte Schriftatlas ist nicht zur öffentlichen Weitergabe vorgesehen.

Die eigene Title-ID lautet `4F4C5043`, nicht die von Lips. `default.xex`
und der zugehörige `media/`-Ordner müssen zusammenbleiben. Die Ausgabe ist
unsignierte Homebrew für eine umgebaute Konsole, keine offiziell signierte
Retail-Anwendung. Das SDK-Entwicklungsimage bleibt separat erhalten. Das
Vorbereitungstool akzeptiert nur die eigene Client-Title-ID und verändert
keine ausführbaren Spieldateien.

## Teststand

Die native OpenLips-Oberfläche wurde in Xenia dargestellt. Host-Transporttests
prüfen anonymes HTTP, Katalog, verifizierten Download, Offline-Cache,
Content-Zwischenablage mit Rückleseprüfung und den Schutz vorhandener Dateien.
**Start unter Aurora, Controller-Bedienung, Erkennung zwischen Geräten,
Coverdarstellung und tatsächliche DLC-Installation auf der Xbox müssen noch
auf echter Hardware getestet werden.** Ein erfolgreicher Build oder
Emulator-Screenshot bestätigt diese Punkte nicht.

Siehe [Bibliothek einrichten](../library_server/README.de.md) und
[API-Dokumentation](../docs/xbox_library_server.de.md).
Der anonyme Dienst gehört ins vertrauenswürdige Heimnetz, ohne Internet-Portweiterleitung.
