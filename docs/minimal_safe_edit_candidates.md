# Minimal Safe Edit Candidates

Stand: 2026-07-06

Quelle: `tools/runtime_test_prep.py`, lokaler Output unter `private/outputs/roundtrip_batch/`.

Wichtig: In diesem committed Doc sind Originalwoerter aus Lyrics bewusst redacted. Exakte Originalwoerter stehen nur im ignored privaten Report `private/outputs/roundtrip_batch/minimal_edit_candidates_private.json`.

## Ziel

Noch keinen Runtime-Test und keine Dateiaenderung durchfuehren. Nur moeglichst risikoarme Kandidaten fuer eine spaetere gleichlange Text-Payload-Aenderung finden.

Suchkriterien:

- Lips-1 Plain-IXB Lyric-Dateien
- ausgewaehlte Textressource per Chart-WordData-Coverage
- kurze ASCII-Woerter
- aktuell nur 4 Zeichen
- Wort kommt eindeutig in der ausgewaehlten Payload vor
- gleichlange Ersatzwoerter moeglich
- unmittelbare Naehe zu Hash-/Length-/Pointer-Feldern diagnostisch reporten

## Ergebnis

Fakten:

- Kandidaten gefunden: 40
- Alle Kandidaten stammen aus Textressourcen mit Coverage `1.0`.
- Alle Kandidaten sind 4 ASCII-Zeichen lang.
- Alle Kandidaten sind eindeutig innerhalb der ausgewaehlten Text-Payload.
- Keine Datei wurde geaendert.

Oeffentlicher Kandidaten-Report:

- `private/outputs/roundtrip_batch/minimal_edit_candidates_sanitized.json`

Privater Kandidaten-Report mit Originalwoertern:

- `private/outputs/roundtrip_batch/minimal_edit_candidates_private.json`

## Beispielhafte Ersatzwoerter

Die Vorschlagsliste ist bewusst neutral und gleichlang:

- `TEST`
- `NOTE`
- `SING`
- `WORD`
- `PLAY`
- `TONE`
- `LINE`
- `BEAT`

Fuer den ersten echten Test sollte ein Ersatz gewaehlt werden, der exakt dieselbe Byte-Laenge hat. Bei ASCII 4 -> 4 ist das trivial, solange keine UTF-8-Mehrbyte-Zeichen genutzt werden.

## Feldnaehe

Der Kandidatenreport enthaelt pro Kandidat:

- `candidate_id`
- `pair_id`
- `word_hash`
- `length`
- `replacement_examples`
- `unique_in_selected_payload`
- `selected_resource_index`
- `coverage_ratio`
- `nearby_field_offsets_within_32_bytes`
- `payload_hash_field_in_same_resource`
- `payload_length_field_in_same_resource`
- `pointer_like_refs_into_payload_count`
- `payload_length_value_refs_count`

Interpretation:

- `nearby_field_offsets_within_32_bytes = 0` ist fuer den ersten gleichlangen Test attraktiver.
- Nicht-null heisst nicht automatisch gefaehrlich, aber der Kandidat liegt naeher an bekannten/diagnostischen Feldern.
- Hash-/Length-Felder existieren in derselben Ressource weiterhin. Gleichlange Edits vermeiden Laengenupdates, aber das Hash-Feld bleibt ein Runtime-Risiko.

## Auswahl fuer den ersten Runtime-Test

Empfohlen:

1. Kandidat mit `length=4`.
2. `unique_in_selected_payload=true`.
3. `coverage_ratio=1.0`.
4. `nearby_field_offsets_within_32_bytes=0`.
5. Gleichlanger ASCII-Ersatz.
6. Aenderung nur an einer Kopie, niemals am Original.

Nicht empfohlen:

- Textlaenge aendern.
- Mehrere Woerter gleichzeitig aendern.
- Nicht-ASCII einsetzen.
- Hash-/Length-Felder raten.
- Pointer-like refs veraendern.

## Tests Nach Phase 2

- `python3 -m compileall tools tests`: bestanden.
- `python3 -m pytest`: nicht ausgefuehrt, weil `pytest` in der lokalen Python-Umgebung nicht installiert ist.
