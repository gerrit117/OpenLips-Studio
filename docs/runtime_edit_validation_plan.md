# Runtime Edit Validation Plan

Stand: 2026-07-06

Quelle: `tools/runtime_test_prep.py`, lokaler Dry-Run unter `private/outputs/roundtrip_batch/validation_dry_run.json`.

Keine Gamefiles wurden geaendert oder kopiert. Der Dry-Run vergleicht dieselben Originalbytes gegen sich selbst, um das Analyzer-before/after-Framework zu pruefen.

## Ziel

Vor einem echten Runtime-Test soll ein lokaler Workflow bereitstehen, der Original und spaetere Kopie automatisch analysiert und writer-relevante Invarianten vergleicht.

Noch nicht enthalten:

- Kein Editor.
- Kein Patch.
- Keine Hash-Reparatur.
- Keine Neuserialisierung.

## Aktueller Dry-Run

Fakten:

- Status: ok
- Vergleich: same-bytes
- Diff Count: 0

Damit ist die Vergleichsinfrastruktur fuer einen spaeteren Original-vs-Kopie-Lauf vorbereitet.

## Verglichene Invarianten

Der Snapshot enthaelt:

- Chart Header:
  - `IsBigEndian`
  - `IsText`
  - `Platform`
  - `NumOfElements`
- Lyric Header:
  - `IsBigEndian`
  - `IsText`
  - `Platform`
  - `NumOfElements`
- Chart-Class-Inventar als SHA1 ueber Klassennamen
- Lyric-Class-Inventar als SHA1 ueber Klassennamen
- Chart-/Lyric-Class-Counts
- Marker Counts:
  - Melody
  - Lyric
- Ausgewaehlte Textressource:
  - Auswahlmethode
  - Resource Index
  - Coverage Ratio
- Textressourcen:
  - Payload Length
  - Visible Length
  - Hash-like Field
  - Hash Offset
  - Payload-Length Offset
  - Pointer-like refs count
  - Payload-Length value refs count
  - Coverage Ratio

## Erwartung fuer einen spaeteren gleichlangen Textedit

Bei einem minimalen 4->4 ASCII-Edit sollte idealerweise stabil bleiben:

- Header
- Classes
- `NumOfElements`
- Marker Counts
- Text Coverage
- Payload Lengths
- Pointer-like refs counts
- Payload-Length refs counts

Wahrscheinlich aendern kann sich:

- Textpayload-Bytes
- SHA1 der gesamten Datei
- eventuell payload-hash-artiges Feld, falls der Edit-Workflow es spaeter bewusst aktualisiert

Blocker, falls sie auftreten:

- Coverage faellt unter 100%.
- Payload Length aendert sich.
- Marker Counts aendern sich.
- Class-Inventar aendert sich.
- Parser findet Textressource nicht mehr.

## Lokaler Workflow fuer den ersten echten Test

1. Original unveraendert lassen.
2. Private Kopie ausserhalb von Git/unter `private/outputs/` erstellen.
3. Genau einen 4->4 ASCII-Kandidaten in der Kopie aendern.
4. Analyzer-Snapshot Original erzeugen.
5. Analyzer-Snapshot Kopie erzeugen.
6. Diffs pruefen.
7. Nur wenn die erwarteten Invarianten stabil bleiben: Runtime-Test mit Kopie vorbereiten.

## Phase 4: Konkrete Ghidra-Blockerfragen

Nur diese gezielten Fragen sind jetzt sinnvoll:

1. Welche Funktion validiert das payload-hash-artige Feld direkt vor Textpayloads?
2. Welche Funktion schreibt `ixRawFileImage` Payload Length und Hash?
3. Welche Payload-Length-Value-Refs sind echte Referenzen, und welche sind zufaellige Werttreffer?
4. Welche Padding-Regel gilt fuer Textpayloads in `ixRawFileImage`?
5. Wird das Hash-Feld beim Laden hart validiert oder nur fuer Caching/Resource Identity genutzt?

Keine breite neue Ghidra-Suche noetig, bis ein gleichlanger Edit im Analyzer-Diff unerwartete Abweichungen zeigt.

## Private Outputs

Ignored/private:

- `private/outputs/roundtrip_batch/validation_dry_run.json`

## Tests Nach Phase 3

- `python3 -m compileall tools tests`: bestanden.
- `python3 -m pytest`: nicht ausgefuehrt, weil `pytest` in der lokalen Python-Umgebung nicht installiert ist.
