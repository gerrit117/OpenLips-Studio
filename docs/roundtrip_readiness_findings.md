# Roundtrip Readiness Findings

Stand: 2026-07-06

Quelle: `tools/corpus_comparison.py` Phase 3, lokaler privater Output unter `private/outputs/corpus_comparison/roundtrip_noop_probe.json`.

Keine privaten Pfade, Songtitel, Lyrics oder Rohdaten werden hier dokumentiert.

## Ziel

Noch keinen Editor bauen. Nur pruefen, ob eine kleine Plain-IXB Lyric-Datei in Sections getrennt und byte-identisch wieder zusammengesetzt werden kann.

## Vorgehen

Der No-op-Test nutzt eine kleine Plain-IXB Lyric-Datei aus dem Lips-1-Dateisystem-Corpus.

Schritte:

1. Bytes lesen.
2. Writer-relevante Tags als Schnittpunkte finden:
   - `<ixb ...>`
   - `<Classes>`
   - `</Classes>`
   - optional `<UriList>`
   - `</UriList>`
   - `<Objects>`
   - `</Objects>`
   - `</ixb>`
3. Nur Byte-Slices bilden.
4. Slices unveraendert wieder zusammenfuegen.
5. SHA1 und Byteidentitaet vergleichen.

Wichtig: Es wurde nichts normalisiert, repariert, formatiert oder neu serialisiert.

## Ergebnis

Fakt:

- Rolle: Lyric
- Datei-Familie: Lips 1-style Plain IXB
- Dateigroesse: 3503 Bytes
- Byte-identisch: ja
- Mismatch-Offset: keiner
- SHA1 original == SHA1 roundtrip

Interpretation:

- Section-Splitting ohne Neuinterpretation ist fuer mindestens eine kleine Plain-IXB Lyric-Datei sicher byte-preserving.
- Das reicht als Grundlage fuer einen spaeteren template-preserving Writer, der unbekannte Bereiche exakt erhaelt.
- Das ist noch kein Beweis, dass Edits sicher sind.

## Was damit jetzt realistisch ist

Naechster sicherer Schritt:

- No-op-Roundtrip auf mehrere Plain-IXB Lyrics ausweiten.
- Danach ein "metadata-preserving" Roundtrip fuer alle 111 Plain-IXB Lyrics laufen lassen.
- Erst dann ein einzelnes bekanntes Scalar-Feld oder eine gleichlange Text-Payload testweise patchen.

Noch nicht realistisch:

- Textlaenge veraendern.
- Object Count veraendern.
- Neue Classes/Members erzeugen.
- Hash-/Length-Felder raten.
- Chart-Objektgraph neu serialisieren.

## Writer-blocking offene Punkte

Fakten aus der Corpus-Phase:

- Jede parsebare Lips-1-Lyric-Datei hat 2 Textressourcen.
- Jede parsebare Lips-1-Lyric-Datei wurde per Chart-WordData-Coverage auf 100% gemappt.
- Payload-Length-Value kommt mehrfach vor.
- Pointer-like refs in Payloadbereiche kommen variabel vor.
- Ein payload-hash-artiges Feld liegt vor dem Textpayload.

Konkrete offene Fragen:

- Welcher Hash-Algorithmus wird fuer das Textpayload-Feld verwendet?
- Ist der Hash hart validiert oder nur Cache-/Resource-Metadatum?
- Welche Length-Refs muessen bei geaenderter Textlaenge aktualisiert werden?
- Welche Pointer-like refs sind echte Objekt-/Payload-Referenzen?
- Welche Padding-Regel gilt fuer `ixRawFileImage` Textpayloads?

## Empfohlene naechste Tests

1. Batch-No-op-Roundtrip fuer alle 111 Plain-IXB Lyric-Dateien.
2. Batch-No-op-Roundtrip fuer Charts nur als Byte-Split/Rejoin, ohne Objektinterpretation.
3. Gleichlange Text-Payload-Aenderung an einer Kopie, mit Analyzer before/after.
4. Erst danach gezielte Ghidra-Analyse fuer Hash/Length/Padding.

## Tests

- `python3 -m compileall tools tests`: bestanden.
- `python3 -m pytest`: nicht ausgefuehrt, weil `pytest` in der lokalen Python-Umgebung nicht installiert ist.
