# Lips `_Lyric.X360` Format Notes

These notes summarize the current read-only analysis of lyric files under
`private/samples`. Do not treat this as a complete writer specification yet.

## Current Conclusion

The unsafe part of the template writer is the automatic `_Lyric.X360` text
payload selection, not chart-side LyricMarker or LyricWordData patching.

Manual same-size raw text replacement works because it changes bytes inside the
existing text resource only. The automatic writer failed because it selected a
larger range than the real text resource in at least some files. That larger
range can include null padding, asset names, path strings, a second `Text`-typed
binary resource, and object metadata after the visible lyrics.

When a matching chart is available, the best current selector is LyricWordData
coverage rather than BOM or printability:

```text
choose the Text resource that contains more than 90% of chart LyricWordData
offset/length ranges
```

This selected the visible lyric payload for every supported plain matching
sample currently available.

## IXB Shape

Observed lyric files are plain IXB:

```text
0x0000  XML IXB schema
...     <Objects>
...     IXB object/resource heap with inline variable-size payloads
...     </Objects></ixb>
```

The schema is self-describing, but a generic fixed-size object walker is not
enough for `_Lyric.X360`. `ixFileImage` / `ixRawFileImage` objects contain
variable-size byte vectors inline. If the walker advances only by the class
size, it will resync into the raw text bytes and report false objects.

Two class layouts have been observed:

```text
Lips 1 style:
  ixPackage size 52
  ixAssetPackage size 72
  ixRawFileImage class index 14

Later/DLC style:
  ixPackage size 72
  ixAssetPackage size 92
  ixVector<ixPackage *> also present
  ixRawFileImage class index 15
```

## Text Resource Layout

The visible lyric text is stored as a length-prefixed `Text` resource. The
current diagnostic recognizes this byte pattern:

```text
u32be  type string length, usually 5
bytes  "Text\0"
bytes  zero padding/alignment
u32be  payload hash / unknown
u32be  payload byte length
bytes  payload
```

The payload byte length is the important boundary. The real visible text range
is inside that payload, usually followed by null padding inside the payload.
The writer must not infer the writable range from a BOM through `</Objects>`.

Important observations:

- Some files start the text payload with a UTF-8 BOM and newline.
- Some files do not have a BOM at the start of the text payload.
- Each matching sample currently has two `Text` resources.
- Only one `Text` resource looks like visible lyric text.
- The second `Text` resource is usually small and mostly binary-looking.
- No sample so far stores duplicate full visible lyric text in `_Lyric.X360`.
- Some resources have an extra alignment byte before the payload length field.
  The parser must score possible alignments instead of accepting the first
  plausible `Text` layout.

## Batch Coverage Summary

This table uses only local private samples and does not include lyric text.

The current batch run covered 58 matching pairs in:

```text
private/samples/lyrics
private/samples/charts
```

Results:

```text
57 supported plain IXB lyric files selected by chart_worddata_coverage
1 compressed lyric file unsupported by structural parser: Irreplaceable_Lyric.X360
0 supported plain files selected below the 90% threshold
2 files where the old heuristic selected no visible candidate, but coverage selected the correct resource:
  ABC
  In Bloom
```

Representative rows:

| Song | Lyric size | Text resources | Visible payload bytes | MelodyMarkers | LyricMarkers | Duplicate lyric-time groups | Best WordData coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| 99 Luftballons | 4918 | 2 | 1846 | 340 | 326 | 0 | 326/326 |
| ABC | 6808 | 2 | 3772 | n/a | 1150 | many | 1150/1150 |
| Any Dream Will Do | 4543 | 2 | 1015 | 427 | 400 | 163 | 400/400 |
| Every Little Thing She Does Is | 5091 | 2 | 2001 | 466 | 443 | 0 | 443/443 |
| Everything About You | 4661 | 2 | 1121 | 716 | 642 | 269 | 642/642 |
| I Don't Want To Wait | 6055 | 2 | 2520 | 1460 | 1304 | 529 | 1304/1304 |
| In Bloom | 4606 | 2 | 1560 | n/a | 290 | many | 290/290 |
| The Phantom Of The Opera | 4795 | 2 | 1228 | 626 | 574 | 218 | 570/574 |
| You've Lost That Lovin | 5201 | 2 | 2007 | 891 | 672 | 259 | 672/672 |

`WordData coverage` means how many parsed chart LyricMarkers have text
offset/length ranges that fit inside the candidate visible lyric payload.

The Phantom Of The Opera has four parsed LyricMarkers outside the candidate
text payload. Those records may be false positives from the current LyricMarker
scanner or a layout variant that is not decoded yet.

## Why Manual Replacement Worked

The manual proof-of-concept was a same-size raw replacement. That means:

```text
same byte range
same payload length field
same IXB object heap
same pointers / vector metadata
same file size
same object count
```

As long as the replacement stays inside the true text payload, this is the
least invasive edit.

## Why Automatic Text Replacement Failed

The previous automatic logic treated the lyric text as:

```text
first BOM byte through before </Objects>
```

That is not the same as the real resource payload. In `Any Dream Will Do`, for
example, the structural `Text` resource payload is 1015 bytes. The broader
BOM-to-objects-end range runs beyond that resource into later heap data.

Consequences:

- The writer can overwrite bytes after the text resource.
- It can alter padding or binary resource data that the game expects.
- It can erase or replace object metadata without changing file size, which
  still corrupts the IXB heap semantically.
- BOM-based detection fails for files whose visible text resource has no BOM.

## Chart Correlation

Chart `.X360` files carry the gameplay mapping:

```text
lpsLyricMarker -> lpsLyricWordData offset/length -> decoded lyric text
lpsLyricMarker -> lpsMelodyMarker
lpsMelodyMarker -> timing/pitch
```

The current evidence says LyricWordData offsets are character offsets into the
decoded visible lyric payload, not raw byte offsets. This is especially
important for UTF-8 text.

For most matching samples, every parsed LyricMarker text offset fits the single
visible lyric payload. That suggests `_Lyric.X360` usually stores the visible
text once, while chart files may contain repeated or mode-specific marker data.

## Modes, Players, and Duplicates

Gameplay supports Single, VS, Duet, short, and long/full modes. The samples do
not yet expose explicit labels for those modes in `_Lyric.X360`.

Current clues:

- `99 Luftballons` has no duplicate LyricMarker time groups.
- Later/DLC samples have many duplicate LyricMarker time groups, often with
  groups of two or three at the same time.
- Those same files still appear to have one visible lyric text payload.
- `track_index` values in parsed LyricMarkers look pitch-like in known charts,
  not like a simple player/mode enum.

Working hypothesis:

```text
_Lyric.X360 stores the visible text once.
Chart files contain the duplicate/mode/player/voice timing mappings.
Short/long/duet/single/vs selection likely happens through chart-side marker
groups, linked objects, or higher-level mode data that is not decoded yet.
```

Do not assume this is final. A future analyzer pass should identify the owning
objects around LyricMarkers and MelodyMarkers, not just individual records.

## Diagnostic Tool

Use:

```bash
python tools/analyze_lyric_file.py "private/samples/lyrics/Any Dream Will Do_Lyric.X360" --chart "private/samples/charts/Any Dream Will Do.X360"
```

Batch mode:

```bash
python tools/analyze_lyric_file.py --batch private/samples/lyrics --charts private/samples/charts
```

The tool prints:

- file size and IXB magic
- IXB class names and sizes
- ASCII/UTF-8 ranges
- `Text` resources and payload length fields
- candidate visible lyric payload ranges
- duplicate visible lyric resources
- pointer-like references into payloads
- payload length value references
- selected text resource and `selected_by=chart_worddata_coverage` when a
  matching chart is supplied
- matching chart MelodyMarker/LyricMarker counts
- duplicate LyricMarker time groups
- track/pitch-like value distribution
- LyricWordData coverage against each text resource

## Writer Implications

Do not build a new text writer until the analyzer is used on more samples.

When text writing resumes, it should:

```text
parse the Text resource record
use the resource payload length field
choose the payload by chart WordData coverage when a matching chart is present
require more than 90% WordData coverage before writing
fallback to heuristic selection only when no chart is available
preserve file size
preserve payload length fields unless intentionally updated later
write only inside the true payload byte range
account for UTF-8 byte length and character offsets separately
avoid BOM-only detection
avoid </Objects>-bounded text replacement
```

## Open Questions

- What does the payload hash / unknown field before the payload length mean?
- Are the payload length duplicate values later in the heap cached sizes,
  reserve sizes, or copied vector metadata?
- Which owning chart objects group MelodyMarkers and LyricMarkers by mode,
  player, duet voice, or short/full arrangement?
- Are the four Phantom out-of-range LyricMarkers false positives or a real
  alternate lyric mapping structure?
- Does any sample contain multiple true visible lyric payloads for duet or
  language variants?
- Does the game validate hashes for `_Lyric.X360` text resources, or only the
  length/vector metadata?
