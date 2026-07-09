# Batch Roundtrip Findings

Stand: 2026-07-06

Quelle: `tools/runtime_test_prep.py`, lokaler Output unter `private/outputs/roundtrip_batch/`.

Keine Gamefiles wurden veraendert. Keine privaten Pfade, Songtitel, Lyrics oder Rohdaten werden hier dokumentiert.

## Ziel

Vorbereitung eines ersten echten template-preserving Runtime-Tests mit minimalem Risiko:

- Plain-IXB Lyrics: parse -> Section-Split -> unveraendertes Rejoin -> SHA1/Bytevergleich
- Plain-IXB Charts: gleicher Test, aber ohne Objekt-Neuserialisierung
- Keine Auto-Fixes, keine Normalisierung, keine Writer-Logik

## Methode

Verwendet wurden die bestehenden Reader/Analyzer:

- `load_lips1_filesystem_pairs`
- `describe_magic`
- `parse_ixb_document`
- `validate_ixb_write_order`
- bestehendes byte-slice-basiertes Section-Splitting

Die Sections wurden nur als originale Byte-Slices getrennt und direkt wieder zusammengefuegt:

- `<ixb ...>`
- `<Classes>`
- `</Classes>`
- `<UriList>`
- `</UriList>`
- `<Objects>`
- `</Objects>`
- `</ixb>`

## Ergebnis

| Rolle | Dateien | Byte-identisch | Erste Abweichung |
| --- | ---: | ---: | --- |
| Lyric Plain-IXB | 111 | 111 | keine |
| Chart Plain-IXB | 111 | 111 | keine |

Fakten:

- 111/111 Plain-IXB Lyric-Dateien roundtrippen byte-identisch.
- 111/111 Plain-IXB Chart-Dateien roundtrippen byte-identisch.
- SHA1 original == SHA1 roundtrip fuer alle getesteten Dateien.
- Es gab keine erste Abweichung und damit keine betroffene Section zu reporten.

Interpretation:

- Section-Split/Rejoin ist fuer die Lips-1 Plain-IXB-Familie batch-stabil.
- Das bestaetigt, dass ein spaeterer template-preserving Workflow unbekannte Bytes exakt erhalten kann.
- Das bestaetigt noch nicht, dass Edits sicher sind.

## Private Outputs

Ignored/private:

- `private/outputs/roundtrip_batch/batch_roundtrip_lyrics.json`
- `private/outputs/roundtrip_batch/batch_roundtrip_charts.json`
- `private/outputs/roundtrip_batch/batch_roundtrip_summary.json`

Die Reports enthalten nur Pair-IDs, Rolle, Groessen, SHA1-Werte, Byteidentitaet und eventuelle Mismatch-Metadaten.

## Tests Nach Phase 1

- `python3 -m compileall tools tests`: bestanden.
- `python3 -m pytest`: nicht ausgefuehrt, weil `pytest` in der lokalen Python-Umgebung nicht installiert ist.
