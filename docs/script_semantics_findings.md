# Script semantics findings from private Lips game corpus

Source: local private corpus under `private/Lips/`, scanned on 2026-07-03.

Privacy boundary: this document contains only structured summaries. It does not
quote script bodies, lyrics, song metadata rows, or original binary data. Detailed
machine-readable local reports are under
`private/outputs/game_corpus_analysis/` and are intentionally private.

## Scope

- Script-like files scanned: 149 `.lua` source files and 53 `.luaB` files.
- `.lua` files were scanned as text.
- `.luaB` files were scanned only at an identifier/string level; they were not
  decompiled and should be treated as weaker evidence.
- The first-game tree (`lps/Script`) contains readable Lua source. The LS2 tree
  (`Ls2/Script`) is mostly `.luaB`.

## High-value script areas

The most relevant source directories/files for song/chart semantics are:

| Area | Why it matters |
| --- | --- |
| `lps/Script/MusicDatabase.lua` | Bridges song database fields to runtime song/chart/audio URIs. |
| `lps/Script/SequenceTrackConfig.lua` | Strongest readable script hint for track, sequence, marker, lyric, melody, and audio grouping. |
| `lps/Script/Chart/` | Runtime chart display, lyric rendering, marker rendering, scoring, phrase fill, short mode, and timing UI. |
| `lps/Script/AgentGraphs/ChartDisplayAPI.lua` | UI-facing chart/lyric/marker API surface. |
| `lps/Script/LpsUtilities.lua` | Shared utility layer with chart, lyric, gesture, phrase, hit marker, audio, and X360 references. |
| `lps/Script/SongToXLAST.lua` | Build/export-oriented naming hint; only light direct term hits in the scan. |
| `lps/Script/ConvertConfig.lua` | Contains X360 conversion/config references. |

## Term evidence

Identifier/string-level term counts across Lua/LuaB files:

| Term | Hits | Files with hits |
| --- | ---: | ---: |
| `Chart` | 5314 | 116 |
| `Lyric` | 2743 | 36 |
| `Marker` | 1443 | 48 |
| `Sequence` | 1364 | 26 |
| `Gesture` | 971 | 21 |
| `Noisemaker` | 467 | 23 |
| `Audio` | 376 | 14 |
| `Phrase` | 310 | 29 |
| `Uri` | 309 | 30 |
| `Track` | 267 | 15 |
| `MusicDatabase` | 214 | 22 |
| `HitMarker` | 151 | 20 |
| `LyricMarker` | 70 | 6 |
| `MelodyMarker` | 51 | 5 |
| `Quick` | 51 | 8 |
| `AudioUri` | 22 | 2 |
| `LyricUri` | 10 | 2 |
| `ChartUri` | 9 | 2 |
| `X360` | 5 | 3 |
| `ixb` | 1 | 1 |

Important limitation: the term scan proves vocabulary and likely semantic
neighborhoods. It does not prove binary field offsets or IXB object layout.

## Music database field links

Readable first-game database/script evidence lines up with the SQLite schema:

- `lps/MusicDB` has one `Music` table with song identity, metadata, asset URI,
  content, state, date, leaderboard, locale, and fog fields.
- The song runtime fields most directly tied to IXB/X360 files are:
  `ChartUri`, `LyricUri`, `AudioUri`, `VideoUri`, `AlbumJacketUri`,
  `PreviewAudioUri`, `PreviewVideoUri`, `PreviewIconUri`,
  `ChartContentFilename`, and `VideoContentFilename`.
- `lps/Script/MusicDatabase.lua` contains hits for `ChartUri`, `LyricUri`,
  `AudioUri`, `Uri`, `Chart`, `Lyric`, and `Audio`, making it the best script
  entry point for connecting DB rows to runtime resource loading.
- `Ls2/MusicDb2*.db3` splits the first-game `Music` table shape into
  `MusicData`, `StageData`, `PreviewData`, and `DLCData`.

Concrete schema details are summarized in `docs/game_corpus_findings.md`.

## Marker and sequence semantics

The readable script names and IXB class names agree on the main chart concepts:

- Chart rendering scripts reference marker classes used by the existing analyzer:
  `lpsMelodyMarker`, `lpsLyricMarker`, `lpsPhraseMarker`, `lpsHitMarker`,
  `lpsPageBreakMarker`, and `lpsShortEndMarker`.
- `SequenceTrackConfig.lua` is the strongest script-side evidence that these are
  organized through sequence/track concepts rather than as a flat marker list.
- `ChartRenderer.lua`, `LyricRenderer.lua`, `PhraseMarker.lua`, and
  `HitMarker.lua` are the most direct readable UI/runtime consumers of the
  marker vocabulary.
- The Lua scan has `Quick` hits, but this is not enough evidence yet to identify
  a binary quick-action object or to remove it safely from generated files.

## Connection to IXB analyzer fields

The script/database layer supports the current analyzer direction:

- `ChartUri` maps to chart IXB/X360 resources.
- `LyricUri` maps to visible lyric IXB/X360 resources.
- `AudioUri` and preview fields map to external audio/video/image resources, not
  to the chart object heap itself.
- Marker semantics belong in chart files, while visible lyric text belongs in
  lyric files. This matches the current `analyze_lyric_file.py` split where the
  lyric file is inspected together with an optional chart file.

## Facts vs hypotheses

Facts:

- The first-game `lps/MusicDB` stores chart and lyric references as `.ixb`
  logical URIs.
- The game folder stores many corresponding resources as `.X360` files.
- The readable first-game scripts contain explicit chart, lyric, marker,
  sequence, track, and URI vocabulary.
- `SequenceTrackConfig.lua` is a high-value script file for track/sequence
  mapping.

Hypotheses:

- The `.ixb` URI suffix in the DB is probably a logical resource identity, while
  `.X360` is the packaged/on-disc container extension.
- Quick-action data may be optional for a first-game-style writer, but the
  current script scan does not prove where quick actions live in the binary
  files.
- Track/sequence script names likely correspond to IXB `ixSequence`,
  `ixSeqCode`, and marker-code classes, but exact per-field mapping still needs
  object-heap analysis.

## Next steps

1. Build a local-only semantic extractor for `lps/MusicDB` that emits sanitized
   schema/URI patterns and can join DB rows to existing chart/lyric analyzer
   summaries without outputting titles, artists, lyrics, or filenames.
2. Use `SequenceTrackConfig.lua` as the script-side map for classifying IXB
   sequence tracks, but validate each field against object-heap bytes before
   changing parser assumptions.
3. Extend the existing analyzer reports with a "resource role" column derived
   from DB fields: chart, lyric, audio, video, preview audio, preview video,
   preview icon, album jacket.
4. Keep quick-action handling diagnostic until we can identify an IXB class,
   member, or stable object pattern tied to it.
