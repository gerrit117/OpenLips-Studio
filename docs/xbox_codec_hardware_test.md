# Codec-Test Auf Der Echten Xbox 360

Die bisherigen Ergebnisse aus Xenia sind kein Nachweis für die echte Konsole.
Der Test verwendet die private, leere **Number One Hits Custom Edition**, nicht
die Xenia-Only-Kopie. ISO, originale Spieldateien und Spielstände bleiben erhalten.

## Vergleichspakete

`python -m tools.build_xbox_codec_tests --out NEUER_ORDNER` erzeugt sechs DLCs
mit selbst erzeugten 70-Sekunden-Testbildern und Sinuston, ohne Originalsongs:

1. **Original:** normaler Studio-Export, WVC1 mit eingebettetem WMA Pro.
2. **Remux-Kontrolle:** gleiche komprimierte Video-/Audio-Nutzdaten, anderer ASF-Muxer.
3. **MP4S:** echtes MPEG-4 Part 2, unverändertes eingebettetes Referenzaudio.
4. **MP43:** echtes Microsoft MPEG-4 v3, unverändertes Referenzaudio.
5. **MP42:** echtes Microsoft MPEG-4 v2, unverändertes Referenzaudio.
6. **WMA Standard:** unverändertes WVC1-Video, nur eingebettetes Audio geändert.

Chart, Lyrics, Cover, separate xWMA-Songdatei und Vorschauen sind bytegleich.
Titel/Song-IDs sind zur Unterscheidung verschieden. Alle Vorschauvideos behalten
absichtlich das Originalformat: Eine funktionierende Vorschau bestätigt deshalb
nicht den Codec des vollständigen Songs. Das isoliert den eigentlichen Test.
Die `tests.json` enthält Dateinamen und Hashes. Ein bestandener Container- und
FFmpeg-Test bestätigt nur die Vorbereitung, noch keine Abspielbarkeit in Lips.

## Ablauf

- Zuerst Originalkontrolle übertragen und in NoH bis zum Ende spielen. Ohne
  funktionierende Kontrolle keine Codec-Schlüsse ziehen.
- Danach Remux-Kontrolle bis mindestens 65 Sekunden, besser bis zum Ende testen.
  Friert nur diese ein, steht der ASF-Muxer beziehungsweise dessen Metadaten im
  Vordergrund, nicht zunächst der Videocodec.
- Anschließend jede weitere Variante testen. Titel, Bildbewegung, Ton, Songuhr,
  Fehlermeldung und gegebenenfalls Zeitpunkt des Einfrierens notieren/filmen.
- Zwischen Versuchen zum Dashboard zurückkehren und NoH neu starten. Keine
  weitere Spielversion starten und keine bestehenden Spielstände löschen.
- Ein Paket nach dem anderen ist der übersichtlichste Test. Bestehende Inhalte
  nicht automatisch löschen oder überschreiben. Studio kopiert explizit
  ausgewählte Pakete über FTP; Ergebnisse werden nicht als kompatibel markiert.

## XBDM Mit Aurora

Ein eingerichtetes XBDM-Plugin ermöglicht Diagnose über das LAN. Der eigene
Collector verwendet nur `dmversion`, `modules`, `threads` und `threadinfo`:

```powershell
python -m tools.xbdm_snapshot --host XBOX_IP --out private/snapshot.json --xex "PFAD\default.xex"
```

Er pausiert das Spiel nicht, setzt keine Breakpoints, liest keine CPU-Schlüssel,
schreibt keinen Speicher und startet keine Titel. Antwortgröße und Timeouts
sind begrenzt. Vor einem Versuch, während funktionierender Wiedergabe und nach
einem Fehler je einen Snapshot mit neuem Dateinamen anlegen. Port ist regulär
TCP `730`. XBDM gehört ausschließlich ins vertrauenswürdige LAN, nie ins Internet.

**Grenze:** Modul-/Threadlisten zeigen nicht automatisch den Decoder-Returncode
oder den vollständigen Aufrufstack. Für die Ursache braucht es danach gezielte
NoH-Analyse, unterstützte Debug-Breakpoints/Register oder eine abgesicherte
Diagnose-Instrumentierung. Die bisherigen OG-XEX-Adressen dürfen nicht einfach
für NoH verwendet werden. Erst NoH-Hash, Version und Modulbasis abgleichen.
Debug-Fähigkeiten unterscheiden sich zwischen XBDM-Plugins.

Als Referenz dienen die offenen Implementierungen
[Experiment5X/XBDM](https://github.com/Experiment5X/XBDM/blob/master/Xbdm.cpp)
für die Abfragen und [EmDbg](https://github.com/InvoxiPlayGames/EmDbg) für
weitergehende Debug-Funktionen. EmDbg beschreibt sich selbst als unfertiges
Werkzeug. Es wird hier nicht automatisch installiert; kein XDK/SDK oder
Spielcode wird mitgeliefert.

Der lokale Launcher `OpenLips Custom Edition/Diagnose-Xbox.cmd` fragt nach der
Xbox-IP und legt private Snapshots mit Zeitstempel ab. Hardwareverbindung und
Plugin-Kompatibilität bleiben bis zum tatsächlichen Konsolentest unbestätigt.
