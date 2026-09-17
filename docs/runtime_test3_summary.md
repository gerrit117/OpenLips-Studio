# Runtime Test 3 Summary

Stand: 2026-07-09

Ziel: dritter kontrollierter Konsolen-Runtime-Test mit minimalem Risiko, diesmal aus dem wiederhergestellten `private/Lips/lps/Levels`-Corpus und ohne `ANZ`.

## Sanitized Testdaten

- Candidate-ID: `1b0b91250b56`
- Rolle: Lyric
- Edit-Typ: 4 ASCII Bytes -> 4 ASCII Bytes
- Dateiart: Lips Plain-IXB Lyric
- Region/Familie: nicht-ANZ
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

Ignored/private unter `private/outputs/runtime_console_test/test3/`:

- Backup-Kopie der Original-Lyric-Datei
- Gepatchte Lyric-Kopie
- `console_test_instructions.md`
- `reports/before_snapshot.json`
- `reports/after_snapshot.json`
- `reports/diff_report.json`
- `reports/candidate_manifest_private.json`

## Erwarteter Runtime-Effekt

Ein einzelnes sichtbares 4-Zeichen-Lyric-Wort sollte frueh im Song durch den gleichlangen ASCII-Ersatz erscheinen. Timing, Marker, Pitch und Songfluss sollten unveraendert bleiben.
