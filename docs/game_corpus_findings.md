# Game corpus findings from private Lips folder

Source: local private corpus under `private/Lips/`, scanned on 2026-07-03.

Privacy boundary: this document contains only structured summaries. It does not
include original game files, large binary dumps, lyrics, script bodies, or song
metadata row dumps. Detailed local reports are under
`private/outputs/game_corpus_analysis/` and are intentionally private.

## Repository safety

- `.gitignore` explicitly ignores `private/`, `private/lips/`, and
  `private/Lips/`.
- The analysis did not move, copy, or modify game files.
- Generated local reports are under `private/outputs/game_corpus_analysis/`.

## Corpus inventory

Total files: 3354.

Top-level distribution:

| Path | Files |
| --- | ---: |
| `Ls2` | 1925 |
| `lps` | 1395 |
| `ixGameFramework` | 28 |
| Other top-level entries | 6 |

Relevant extension counts:

| Extension | Files |
| --- | ---: |
| `.X360` | 741 |
| `.xma2` | 708 |
| `.nft` | 501 |
| `.xml` | 313 |
| `.nfmx360` | 223 |
| `.nfacx360` | 214 |
| `.wmv` | 161 |
| `.lua` | 149 |
| `.jpg` | 120 |
| `.xwma` | 119 |
| `.luaB` | 53 |
| `.db3` | 10 |
| no extension | 8 |
| `.ixb` | 2 |

The two no-extension SQLite databases are important: `lps/GameContentDB` and
`lps/MusicDB`.

## SQLite databases

SQLite databases found: 12.

First-game database shape:

| Database | Tables |
| --- | --- |
| `lps/MusicDB` | `Music` |
| `lps/GameContentDB` | `AudioEffectInfo`, `GenericVideoInfo`, `LocalizedStrings`, `MinigameInfo`, `NoisemakerInfo`, `PlayerColorInfo`, `UIThemeInfo` |

`lps/MusicDB.Music` has 40 rows and these writer-relevant fields:

- Identity/metadata: `UintID`, `ID`, `TitleID`, `DiscIndex`, `OwnerXuid`,
  `Title`, `Artist`, `Album`, `Genre`, `Year`, `Rating`, `Length`, `Color`,
  `Language`, `Locale`, `FogID`.
- Main resources: `AudioUri`, `ChartUri`, `LyricUri`, `VideoUri`,
  `AlbumJacketUri`.
- Preview resources: `PreviewLyric`, `PreviewAudioUri`, `PreviewVideoUri`,
  `PreviewIconUri`.
- DLC/content/state: `Source`, `AudioState`, `ChartState`, `VideoState`,
  `ChartContentID`, `VideoContentID`, `ChartContentFilename`,
  `VideoContentFilename`, `ChartReleaseDate`, `VideoReleaseDate`,
  `ChartLatestDate`, `VideoLatestDate`, `Price`, `bPaid`,
  `bKeepUninstalled`, `bSongPackItem`, `bNewItem`, `ChartDeleteCheckFlag`,
  `VideoDeleteCheckFlag`, `LeaderBoardID`.

Observed URI suffix patterns in `lps/MusicDB.Music`:

| Field | Suffix pattern |
| --- | --- |
| `ChartUri` | `.ixb` for all 40 rows |
| `LyricUri` | `.ixb` for all 40 rows |
| `AudioUri` | `.xwma` for all 40 rows |
| `PreviewAudioUri` | `.xwma` for all 40 rows |
| `PreviewVideoUri` | `.wmv` for all 40 rows |
| `PreviewIconUri` | `.nft` for all 40 rows |
| `AlbumJacketUri` | no extension for all 40 rows |
| `VideoUri` | mostly no extension, with one `.wmv` row |

LS2 database shape:

| Database | Tables |
| --- | --- |
| `Ls2/MusicDb2.db3` and 8 region variants | `DLCData`, `MusicData`, `PreviewData`, `StageData` |
| `Ls2/GameContentsDb.db3` | `AudioEffectInfo`, `DiscInfo`, `GenericVideoInfo`, `LocalizedStrings`, `MenuBgmInfo`, `MinigameInfo`, `NoisemakerInfo`, `PlayerColorInfo`, `UIThemeInfo` |

`Ls2/MusicDb2*.db3` splits the first-game `Music` row into:

- `MusicData`: identity, title/artist/album sort fields, genre/language,
  rating, color, album jacket, availability, video flag, type, release date,
  disc/title/song-pack ids, and performance-recording flag.
- `StageData`: `ChartUri`, `AudioUri`, `VideoUri`, `LyricUri`,
  `LeaderBoardId`.
- `PreviewData`: `PreviewAudioUri`, `PreviewVideoUri`, `PreviewLyric`,
  `PreviewIconUri`, `Explicit`.
- `DLCData`: `DLCFilename`, `ContentId`, `Price`, `Paid`, `SellText`.

The LS2 `StageData` and `PreviewData` suffix patterns match the first-game split:
chart/lyric logical URIs are `.ixb`, audio is `.xwma`, preview video is `.wmv`,
and preview icon is `.nft`.

## IXB/X360 structural scan

Files scanned with existing reader/analyzer helpers: 741 `.X360` plus 2 `.ixb`.

Magic/kind distribution:

| Kind | Files |
| --- | ---: |
| `LZXTDECODE compressed` | 432 |
| `plain IXB` | 311 |

Directly parsed plain IXB files:

| Location | Plain IXB | Compressed |
| --- | ---: | ---: |
| `lps/` | 230 | 158 |
| `Ls2/` | 81 | 274 |
| `lps/Levels` | 222 | 2 |
| `Ls2/Levels` | 76 | 11 |

Parsed role distribution:

| Role | Parsed plain IXB files |
| --- | ---: |
| chart/level resource | 149 |
| lyric resource | 149 |
| asset | 11 |
| standalone `.ixb` | 2 |

Header attributes across all 311 parsed plain IXB files:

| Field | Observation |
| --- | --- |
| `Platform` | `WIN32` in all 311 parsed files |
| `IsText` | `false` in all parsed files |
| `IsBigEndian` | `true` in 308 files, `false` in 3 files |
| `UriList` | 0 entries in all parsed files |
| Write-order warnings | none from `validate_ixb_write_order` |

Important interpretation:

- The corpus confirms that real Xbox 360 files may still carry
  `Platform="WIN32"` in IXB metadata. The writer must not blindly force
  `Platform="X360"`.
- `UriList` is absent in all parsed files from this corpus. The writer should be
  able to emit an empty/absent URI list exactly like real samples, while keeping
  URI-list parsing available for counterexamples.
- Compressed files are not parsed internally by the current reader. They need
  decompression before object-heap/class-level analysis.

## IXB class evidence

Common classes across parsed plain IXB chart/lyric resources include:

- Container/base: `ixObject`, `ixReferencedObject`, `ixPackage`,
  `ixTreeNode<ixPackage>`, `ixAssetPackage`, `ixAsset`.
- Chart/resource graph: `lpsMusicInfo`, `lpsMusicIndex`, `ixChart`,
  `lpsChart`, `ixPrototype`, `ixAgentPrototype`.
- Sequence layer: `ixSequence`, `ixSeqCode`, `ixSeqUtilCode`,
  `ixSeqNameTag`, `ixTempoMap`, `ixSeqContentSpecific`, `ixSeqTempoCode`,
  `ixSeqSongSectionPatternCode`, `ixSeqMarkerCode`, `ixSeqController`,
  `ixSeqSuspend`.
- Chart markers: `ixAudioMarker`, `lpsMarker`, `lpsMelodyMarker`,
  `lpsLyricMarker`, `lpsPhraseMarker`, `lpsHitMarker`,
  `lpsPageBreakMarker`, `lpsShortEndMarker`, `Tone`.
- Lyric file payload classes: `ixFileImage`, `ixRawFileImage`.
- Later/LS2-ish additions observed in subsets: `ls2DbRecord`, `ls2MusicData`,
  `ls2LedSequence`, `ls2LedMarkerBandSetting`,
  `ls2LedMarkerBehaviorParam`.
- Gesture/noisemaker related marker classes observed in subsets:
  `lpsTimedGestureMarker`, `lpsTimedNoisemakerMarker`.

Chart/level resources contain the chart and marker classes. Lyric resources
mainly contain package/file-image classes, matching the existing split between
chart marker extraction and lyric text/resource analysis.

## Connection to existing analyzers

The corpus supports the current reader/analyzer extensions:

- `parse_ixb_document` header extraction is useful on real plain IXB files:
  `IsBigEndian`, `IsText`, `Platform`, `NumOfElements`, class range, object
  range, and URI list count all produce stable summaries.
- `validate_ixb_write_order` returns no warnings on parsed corpus files, so the
  Ghidra-derived order check is compatible with these samples.
- Object-record and FileIO-header probes should remain diagnostics. The object
  probe can be very broad on large files and is not a proven object iterator.
- Existing marker extraction must continue to rely on the known object walker
  and class/member sizes, not on the broad diagnostic object-record probe.

## Writer-relevant facts

Facts from private corpus plus existing analyzer output:

- First-game-style song DB rows point to `ChartUri` and `LyricUri` with `.ixb`
  logical suffixes.
- On-disc song resources are commonly `.X360`.
- Parsed chart files contain `lpsChart`, sequence classes, and marker classes.
- Parsed lyric files contain file-image payload classes rather than chart
  marker classes.
- Real parsed IXB metadata uses `Platform="WIN32"` throughout this corpus.
- Parsed song resources have no URI entries in `UriList`.
- Parsed files follow the currently implemented IXB token order checks.

Hypotheses:

- `.ixb` in DB rows is a logical resource URI while `.X360` is the platform
  package/container extension.
- A first-game-style writer should prefer the first-game `lps/MusicDB.Music`
  field model over the LS2 split model when generating metadata.
- Quick actions, if present, likely live in chart/sequence marker-related data,
  but this corpus pass did not identify a reliable quick-action binary class or
  field.

## Concrete next steps for Python code

1. Keep using existing analyzer/parser modules; do not create a parallel parser.
2. Add a local-only corpus joiner that reads `lps/MusicDB`, resolves
   `ChartUri`/`LyricUri` to private files, and feeds those files into
   `analyze_lyric_file.py` and `compare_ixb_structure.py`.
3. Add analyzer output fields for DB-derived resource role and logical URI
   suffix, but keep the DB row values out of committed fixtures/reports unless
   sanitized.
4. For the writer, preserve real template header attributes when using a real
   template, especially `Platform`, `IsBigEndian`, `IsText`, and
   `NumOfElements`.
5. Treat numeric payload serialization as big-endian for parsed song resources
   where `IsBigEndian=true`, matching the previous Ghidra-derived diagnostic
   direction.
6. Do not emit a `UriList` unless a template or future counterexample requires
   it.
7. Investigate compressed `LZXTDECODE` samples only after adding or documenting
   a decompression step; the current reader correctly stops at the outer magic.
