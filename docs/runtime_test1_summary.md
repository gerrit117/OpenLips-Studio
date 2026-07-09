# Runtime Test 1 Summary

Stand: 2026-07-06

Ziel: erster kontrollierter Konsolen-Runtime-Test mit minimalem Risiko.

## Sanitized Testdaten

- Candidate-ID: `1518b459608f`
- Rolle: Lyric
- Edit-Typ: 4 ASCII Bytes -> 4 ASCII Bytes
- Dateiart: Lips-1 Plain-IXB Lyric
- Originaldatei: nicht ueberschrieben
- Patch-Ziel: private Kopie unter `private/outputs/`
- Chart-Datei: unveraendert
- Hash-/Length-/Pointer-Felder: unveraendert

Keine Lyrics, Songtitel oder privaten Pfade werden in diesem Dokument genannt.

## Patch-Pruefung

Fakten:

- Dateigroesse unveraendert: ja
- Geaenderte Bytes: exakt 4
- Nur erwarteter Payload-Bereich geaendert: ja
- Header unveraendert: ja
- Classes unveraendert: ja
- `NumOfElements` unveraendert: ja
- Marker Counts unveraendert: ja
- Coverage bleibt 100%: ja
- Payload Lengths unveraendert: ja
- Pointer-like ref counts unveraendert: ja
- Payload-length ref counts unveraendert: ja
- Hash-like fields bewusst unveraendert: ja
- Analyzer-Diff leer: ja

## Private Artefakte

Ignored/private unter `private/outputs/runtime_console_test/test1/`:

- Backup-Kopie der Original-Lyric-Datei
- Gepatchte Lyric-Kopie
- `console_test_instructions.md`
- `reports/before_snapshot.json`
- `reports/after_snapshot.json`
- `reports/diff_report.json`
- `reports/candidate_manifest_private.json`

## Erwarteter Runtime-Effekt

Ein einzelnes sichtbares 4-Zeichen-Lyric-Wort sollte im Song durch den gleichlangen ASCII-Ersatz erscheinen. Timing, Marker, Pitch und Songfluss sollten unveraendert bleiben.

## Beobachtungspunkte

- Laedt das Spiel?
- Laedt der Song?
- Startet der Song?
- Ist die Lyric sichtbar geaendert?
- Erscheint stattdessen alter Text?
- Bleiben Timing und Marker unveraendert?
- Gibt es Crash, Hang, fehlende Lyrics oder Fallback-Verhalten?

## Wichtig fuer Auswertung

Wenn die Aenderung sichtbar ist, ist ein gleichlanger Textpayload-Edit ohne Hash-Update fuer diesen Fall runtime-tauglich.

Wenn alter Text erscheint, koennte Caching, falscher Deploy-Pfad oder ein anderes Resource-Binding beteiligt sein.

Wenn der Song nicht laedt oder crasht, ist das hash-like Feld oder eine andere Resource-Validierung wahrscheinlich writer-blocking.
