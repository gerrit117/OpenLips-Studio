# Corpus Comparison Findings

Stand: 2026-07-06

Quelle: lokaler Lauf von `tools/corpus_comparison.py` gegen private Daten unter `private/Lips/`. Private Inputs und Detailreports bleiben unter `private/outputs/corpus_comparison/` und sind ignored.

Keine Songtitel, Artists, Lyrics, DB-Rohzeilen oder privaten Dateipfade werden hier dokumentiert.

## Scope und Datenschutz

Umgesetzt:

- `private/Lips/lps/MusicDB` gelesen.
- `ChartUri` und `LyricUri` gehasht und lokal aufloesbar gemacht.
- LS2-Zeilen nicht automatisch als Lips-1-Disc-Songs behandelt.
- DLC/later nicht blind aus `lps/MusicDB` abgeleitet.
- Separat markierter Lips-1-Dateisystem-Corpus unter `lps/Levels` als praktische Analysequelle genutzt, weil die aktuelle `lps/MusicDB` keine Lips-1-URIs enthaelt.
- Bestehende Analyzer/Reader wiederverwendet:
  - `parse_ixb_document`
  - `validate_ixb_write_order`
  - `iter_melody_markers_object_walker`
  - `iter_lyric_markers_structural`
  - `find_text_resources`
  - `select_text_resource`
  - diagnostische Object/FileIO-Probes

Nicht umgesetzt:

- Kein LS2-StageData/PreviewData-Joiner.
- Kein DLC-Joiner.
- Kein neuer Parallel-Parser.
- Keine Edits an Gamefiles.

## Phase 1: Corpus Comparison und DB Joiner

### DB-Befund

Fakt:

- `private/Lips/lps/MusicDB` enthaelt 40 `Music`-Rows.
- Alle 40 `ChartUri`-Werte zeigen auf die Familie `LS2`.
- Im Standardlauf wurden diese 40 Rows deshalb mit `skipped_ls2_optional_later` uebersprungen.

Konsequenz:

- Der angeforderte Lips-1-Disc-Join ueber `lps/MusicDB` ist mit der aktuell lokal vorhandenen DB nicht moeglich.
- Das ist kein Parserfehler, sondern ein Datenquellenproblem.

Praktische Ergaenzung:

- Fuer Phase 1-3 wurde zusaetzlich ein getrennt markierter Lips-1-Dateisystem-Corpus aus `private/Lips/lps/Levels` verwendet.
- Diese Paare sind nicht als DB-Join ausgegeben, sondern als `filesystem_lips1`.

### Laufzahlen

Sanitized Aggregate:

- Total erfasste Paar-Eintraege: 152
- DB-Quelle: 40
- Lips-1-Dateisystemquelle: 112
- Aufgeloeste Lips-1-Dateisystempaare: 112
- Plain-IXB Chart/Lyric-Paare: 111
- Komprimierte/unsupported Chart/Lyric-Paare: 1
- Uebersprungene DB-LS2-Paare: 40

Family Labels:

- `Lips 1-style`: 112
- `LS2`: 40, nur als uebersprungene DB-Zeilen im Standardlauf
- `DLC/later`: 0 im Standardlauf

## Header Attributes

Fakten fuer 111 Plain-IXB Lips-1-Paare:

| Rolle | IsBigEndian | IsText | Platform | NumOfElements |
| --- | --- | --- | --- | --- |
| Chart | `true` bei 111/111 | `false` bei 111/111 | `WIN32` bei 111/111 | variiert stark |
| Lyric | `true` bei 111/111 | `false` bei 111/111 | `WIN32` bei 111/111 | `12` bei 111/111 |

Starke Indizien:

- `IsBigEndian=true` ist fuer Lips-1-Chart/Lyric-Paare stabil.
- `Platform=WIN32` ist auch bei Xbox-360-Dateien normal und darf nicht als Host-Plattform missverstanden werden.
- Lyric-Dateien sind strukturell sehr konstant: `NumOfElements=12`, 14 Klassen, 2 Textressourcen.
- Chart-`NumOfElements` folgt nicht einfach der sichtbaren Markerzahl. Das bestaetigt die bisherige Vorsicht: fuer einen template-preserving Writer erstmal erhalten, nicht neu berechnen.

## Classes / Members Inventories

Fakten:

- Lyrics: 14 Klassen bei 111/111 Plain-IXB-Dateien.
- Charts: 46 bis 63 Klassen, 9 verschiedene Klassenanzahlen.
- Chart-Class-Inventories bilden 24 Varianten.
- Die haeufigsten Chart-Inventories treten mehrfach auf; es gibt also wiederverwendbare Template-Familien.

Starke Indizien:

- Lyric-Dateien sind ein guter erster Roundtrip-/Writer-Kandidat.
- Chart-Dateien brauchen template-family-aware Behandlung. Ein "eine Chart-Struktur fuer alle" waere zu grob.

## Object Section Bounds

Fakten:

- Fuer 222 Plain-IXB-Dateien wurden exakte Section-Bounds privat reportet.
- 222/222 Plain-IXB-Dateien haben keine `validate_ixb_write_order`-Warnung.
- Alle untersuchten Plain-Dateien enthalten eine leere `UriList`-Section.
- `uri_count=0` fuer Charts und Lyrics.

Objektbereich-Groessen:

| Rolle | min | median | max |
| --- | ---: | ---: | ---: |
| Chart Objects | 166322 Bytes | 447250 Bytes | 2239423 Bytes |
| Lyric Objects | 1013 Bytes | 2243 Bytes | 4539 Bytes |

Writer-relevanter Befund:

- Die Ghidra-derived Reihenfolge Header -> Classes -> UriList -> Objects wird durch echte Lips-1-Plain-Samples bestaetigt.
- Fuer diese Familie ist `UriList` vorhanden, aber leer. Ein Writer sollte diese leere Section im Template erhalten.

## Marker Counts

Fakten fuer 111 Plain-IXB-Charts:

| Marker | min | median | max | null |
| --- | ---: | ---: | ---: | ---: |
| MelodyMarker | 159 | 466 | 2661 | 0 |
| LyricMarker | 136 | 453 | 2661 | 0 |

Starke Indizien:

- Jeder parsebare Lips-1-Chart im Corpus enthaelt sowohl Melody- als auch LyricMarker.
- Die bestehenden Analyzer extrahieren fuer diese Familie stabile Markerzahlen ohne neue Parserlogik.

## Text Resource Counts und Coverage

Fakten fuer 111 Plain-IXB-Lyrics:

- Textressourcen pro Lyric-Datei: 2 bei 111/111.
- Ausgewaehlte Textressource: immer per `chart_worddata_coverage`.
- Coverage: 100% bei 111/111.
- Payload-Laengen ueber alle Textressourcen: 84 bis 3983 Bytes.
- Payload-Length-Value-Refs: 1 bis 3 Vorkommen je Ressource.
- Pointer-like refs in Payload-Bereich: 0 bis 19 je Ressource.

Writer-relevanter Befund:

- Chart `LyricWordData` und Lyric-Textressource sind sauber joinbar.
- Textlaengen-/Hash-/Pointer-Felder bleiben writer-blocking fuer echte Edits.
- Ein No-op/byte-preserving Roundtrip ist sinnvoller naechster Schritt; freie Textgroessen-Aenderung noch nicht.

## Payload Length / Hash Fields

Fakten:

- Der vorhandene Lyric-Analyzer findet je Textressource:
  - Payload-Start/Ende
  - Payload-Laenge und Offset des Laengenfelds
  - payload-hash-artiges Feld und dessen Offset
  - Padding-Info
  - Pointer-like refs in den Payload-Bereich
  - Vorkommen des Payload-Length-Werts

Starke Indizien:

- Payload-Laenge ist in echten Lyrics redundant referenziert.
- Hash-/Length-Felder muessen vor echten Textedits gezielt verstanden werden.

Hypothese:

- Das Hash-Feld gehoert sehr wahrscheinlich zur `ixRawFileImage`/Text-Payload-Serialisierung. Algorithmus und Scope sind weiter offen.

## Pointer-like References

Fakten:

- Chart-LyricMarker fuehren zu `LyricWordData`-Offsets mit 100% Coverage in den ausgewaehlten Textressourcen.
- Lyric-Textressourcen selbst enthalten pointer-like refs in variabler Anzahl.
- Die Object-Record-Probe liefert fuer Charts sehr viele Kandidaten und fuer Lyrics wenige Kandidaten.

Wichtig:

- Object-Record-Kandidaten bleiben Diagnose. Die Zahl ist nicht als echte Objektanzahl zu lesen.

## Family Labels

Fakten:

- Standardlauf behandelt nur Lips-1-Dateisystempaare praktisch.
- LS2 aus der aktuell vorhandenen `lps/MusicDB` wurde bewusst nicht analysiert.
- DLC/later wurde nicht blind abgeleitet.

Naechster sauberer Schritt fuer LS2:

- Separater Joiner ueber LS2 `StageData`/`PreviewData`/`DLCData`, nicht ueber `lps/MusicDB`.

## Phase 2: Strict Section-Boundary Report

Privater Output:

- `private/outputs/corpus_comparison/section_boundaries.json`
- `private/outputs/corpus_comparison/section_boundary_summary.json`

Fakten:

- 222 Plain-IXB-Dateien reportet.
- Fuer jede Datei sind vorhanden:
  - `<ixb` Header-Start/Ende
  - `<Classes>` Start/Ende
  - `</Classes>` Start/Ende
  - `<UriList>` / `</UriList>` Start/Ende
  - `<Objects>` / `</Objects>` Start/Ende
  - `</ixb>` Start/Ende
- Write-order-Warnungen: keine bei 222/222.

Interpretation:

- Die Writer-Reihenfolge ist fuer diese Lips-1-Plain-Dateien praktisch verifiziert.
- Der aktuelle Writer sollte exakt diese Section-Reihenfolge template-preserving erhalten.

## Phase 4: Konkrete Ghidra-Fragen aus den Ergebnissen

1. Welche Funktion berechnet oder validiert das payload-hash-artige Feld direkt vor Lyric-Text-Payloads?
2. Welche Native-Struktur schreibt `ixRawFileImage`/Text-Payload-Laenge, Hash und Padding?
3. Welche der mehrfachen Payload-Length-Value-Refs sind echte Referenzen und welche nur zufaellige Werte?
4. Wie berechnet der Serializer `NumOfElements` fuer Chart-Dateien, und warum ist Lyric stabil bei `12`?
5. Was ist die genaue Semantik der drei 4-byte-Felder aus der Object-Record-Probe?
6. Wo wird `UriList` gelesen, und ist eine leere `UriList` fuer Lips-1 zwingend oder nur vom Writer immer emittiert?
7. Wo prueft der Loader `Platform`, `IsBigEndian` und `IsText`, und welche Felder sind hart validiert?

## Tests

- `python3 -m compileall tools tests`: bestanden.
- `python3 -m pytest`: nicht ausgefuehrt, weil `pytest` in der lokalen Python-Umgebung nicht installiert ist.

## Private Outputs

Privat und ignored:

- `private/outputs/corpus_comparison/joined_pairs_sanitized.json`
- `private/outputs/corpus_comparison/corpus_aggregate.json`
- `private/outputs/corpus_comparison/section_boundaries.json`
- `private/outputs/corpus_comparison/section_boundary_summary.json`
- `private/outputs/corpus_comparison/roundtrip_noop_probe.json`
- `private/outputs/corpus_comparison/summary.md`
