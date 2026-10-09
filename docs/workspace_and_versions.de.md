# Ablage und Versionen

## Speichern und Exportieren

- Bei aktivierter Bibliothek landet ein neues Projekt unter `workspace` im
  gewaehlten Bibliotheksordner. Sein Dateiname enthaelt Datum und Uhrzeit.
- Weiteres Speichern aktualisiert diese Arbeitsdatei. **Speichern unter** erlaubt
  einen anderen Speicherort; ohne Bibliothek fragt Speichern nach dem Ort.
- `projects` enthaelt archivierte Projektstaende und `media` gemeinsam genutzte
  Quelldateien. Ein unveraenderter Stand wird nicht erneut archiviert.
- Mit aktivierter Bibliothek werden DLCs direkt unter `publish` erstellt,
  ohne eine weitere Kopie im alten AppData-Bibliotheksordner. Ohne Bibliothek
  fragt der DLC-Export nach dem Zielordner.
- **Ausgewaehlte DLCs kopieren** erzeugt auf ausdruecklichen Wunsch eine
  zusaetzliche Exportkopie. Das Original bleibt fuer Sync/Transfer erhalten.
- Der Community-Export `.ols` fragt weiterhin nach einem Ziel. Er ersetzt
  nicht das editierbare Projekt `.olp` und enthaelt kein Audio/Video.

In der Projektliste stehen Datum, Status und neuester gespeicherter Stand.
**Unfertig** kennzeichnet fehlende Noten/Texte/Tonhoehen/Metadaten sowie
ueberlappende oder nicht unterstuetzte Noten. Ein vollstaendiger Chart ohne
Referenzmedien wird separat gekennzeichnet. **Fuer Export vorbereitet** ist
eine Strukturpruefung, kein Qualitaetsurteil oder garantierter Konsolentest.

## Xbox USB

**Bibliothek > Xbox-USB-Speicher** oder **Werkzeuge > Bibliothek / Xbox >
Xbox-USB-Speicher** zeigt Pakete mit aufklappbarer Songliste. Neue Studio-Pakete
enthalten eine UTC-Erstellungszeit im Header. Bei aelteren Paketen kann nur
eine groebere Ortszeit vorhanden sein; unbekannte Zeiten werden nicht erfunden.
Das USB-Dateidatum kann lediglich der Kopierzeitpunkt sein.

Verglichen werden Pakete mit demselben vollstaendigen Satz aus Interpret und
Titel. Gleiche Paketkennung bedeutet nicht, dass hier alle Mediabytes erneut
gehasht wurden. Unterschiedliche/fehlende Zeitbasen werden nicht automatisch
als neuer oder aelter bewertet. Der Benutzer waehlt, was geloescht wird.
Eine Loeschung betrifft immer das ganze DLC-Paket, bei Packs alle Songs darin.
Andere Spiele, Profile, Spielstaende und lokale Kopien bleiben unangetastet.

## Projektordner

| Bereich | Inhalt |
| --- | --- |
| `studio` | Studio-Quellcode |
| `library_server` | Docker-Bibliothek und WebUI |
| `xbox_client` | Xbox-Client-Quellcode |
| `plugins` | Plugin-Quellen und Dokumentation |
| `tools` | gemeinsam genutzte Format-/Build-Werkzeuge |
| `artifacts/studio/current` | aktueller lokaler Studio-Build und Installer |
| `artifacts/xbox-client/current` | aktueller Xbox-Client |
| `docs` | aktuelle Format-/Workflow-Dokumentation |
| `tests` | automatisierte Tests; lokale Ergebnisse unter `tests/artifacts` |
| `private/runtime` | benoetigte lokale Build-/KI-Abhaengigkeiten |
| `private/research/chart-quality` | laufende Chart-Untersuchung |
| `private/research/noh-extracted` | private Original-Spieldateien, nicht zur Veroeffentlichung |
| `private/tools/LibreLyrics-Desktop` | separates lokales Lyrics-Tool |
| `private/tools/OpenLips-Community` | separate private Website-Repo, nie Teil des Studio-Pushs |
| `private/song-work` | erhaltene private Song-/MIDI-Arbeiten |

Die persoenliche Bibliothek `Documents/Open Lips Library` bleibt eigenstaendig:
sie sind deine Nutzdaten, kein wegzuwerfender Testordner. Fremde Projekte,
SDK-Installationen, persoenliche Dokumente und Schluessel werden nicht bereinigt.
