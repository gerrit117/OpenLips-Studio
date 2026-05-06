# OpenLips Structures Documentation

This document collects the current reverse engineering findings for the Xbox 360 game *Lips*.

The information here is based on analysis of `.X360` chart files, `_Lyric.X360` files, RAM dumps, and runtime object inspection.

## High-Level Architecture

Lips uses several separate data layers:

```text
<Song>.X360        -> chart, melody, pitch, timing, lyric markers
<Song>_Lyric.X360  -> visible lyric text
Runtime memory     -> gameplay/render/scoring objects built from chart data
```

Important conclusion:

```text
Visible text is not the same as gameplay timing.
```

The karaoke cursor / jumping ball is driven by chart markers, especially `lpsMelodyMarker`, not directly by the raw lyric text.

## Container Formats

Known `.X360` variants:

| Magic Bytes | Meaning | Notes |
|------------|---------|------|
| `3C 69 78 62` | Plain IXB (`<ixb`) | directly readable |
| `0F F5 12 ED` | LZXTDECODE compressed | can be decompressed with Xbox 360 SDK tools |
| `0F F5 12 EE` | LZXNATIVE compressed | can be decompressed with Xbox 360 SDK tools |

Most tested Lips song files are plain IXB.

## IXB Format

Example header:

```xml
<ixb IsBigEndian="true" IsText="false" Platform="WIN32">
```

Important properties:

```text
Big Endian
Self-describing class/object format
Embedded class definitions
Heap-like object storage
Original memory-style pointers
```

## lpsMelodyMarker

Main gameplay note / pitch object.

Runtime vtable:

```text
0x8200D8D0
```

Size:

```text
36 bytes
```

Runtime layout:

```text
+0x00  vtable              0x8200D8D0
+0x04  ref/id
+0x08  time                float BE, seconds
+0x0C  length              float BE, seconds
+0x10  raw_pitch           int BE
+0x14  unknown/bool
+0x18  tone                float BE
+0x1C  octave              int BE
+0x20  tilt                int/bool
```

Example object:

```text
82 00 D8 D0
00 00 00 02
41 0D B2 8A
3E BA 58 A0
00 00 00 31
00 00 00 00
40 C0 00 00
00 00 00 06
00 00 00 00
```

Decoded:

```text
time      = 8.856088 s
length    = 0.363957 s
raw_pitch = 49
tone      = 6.0
octave    = 6
tilt      = 0
```

## Melody / Pitch Findings

For `99 Luftballons`, 340 MelodyMarker objects were found.

Observed runtime area:

```text
0x407C....
```

The runtime MelodyMarkers match the data extracted from the `.X360` chart file.

## Runtime Wrapper Object

Additional runtime object associated with melody notes.

Vtable:

```text
0x8200D490
```

Observed layout:

```text
+0x08  time
+0x0C  length
+0x10  raw_pitch
+0x18  pointer -> lpsMelodyMarker
```

Example:

```text
0x407CDC18 -> 0x407CDBC0
```

This appears to be a gameplay/scoring/render wrapper around a MelodyMarker.

## Runtime NoteNode

Runtime gameplay/render note node.

Vtable:

```text
0x820110DC
```

Size:

```text
0x20 bytes
```

Observed count in one dump:

```text
880
```

Observed layout:

```text
+0x00  vtable              0x820110DC
+0x04  render/display time
+0x08  tone
+0x0C  octave
+0x10  linked node pointer
+0x14  pointer -> lpsMelodyMarker
+0x18  unknown
+0x1C  next time/cache/unknown
```

This is not the original chart object. It appears to be a runtime render/gameplay structure.

Observed RAM area:

```text
0x4153....
```

## Companion Runtime Object

Additional runtime object found in the same general area as NoteNodes.

Vtable:

```text
0x8207EE90
```

Size appears to be:

```text
0x20 bytes
```

Purpose is not fully understood.

Possible role:

```text
lyric helper
render helper
companion object
runtime cache object
```

Warning:

Many values inside these objects look pointer-like but are actually floats. Do not blindly treat every `0x40......` or `0x41......` value as a pointer.

## lpsLyricMarker

Lyric-to-note mapping object.

Found in chart data:

```text
326 markers
```

Size:

```text
64 bytes
```

Observed layout:

```text
+0x00  class/vtable-ish
+0x04  refcount
+0x08  trigger time
+0x0C  display length / syllable duration
+0x10  unknown / track-ish
+0x18  pointer -> lpsMelodyMarker
+0x1C  vector -> lpsLyricWordData
+0x20  vector reserve/capacity related
+0x24  vector size/count related
+0x28  allocator/unknown
+0x2C  string/freeword related
+0x3C  endOfWord
```

Important relationship:

```text
lpsLyricMarker +0x18 -> lpsMelodyMarker
```

This maps a lyric syllable to a melody note.

## lpsLyricWordData

LyricWordData is referenced by the vector inside `lpsLyricMarker`.

Observed important fields:

```text
+0x00  object/class-ish
+0x04  character offset
+0x08  character length
+0x0C  flags
+0x10  style/hash/unknown
```

Important:

```text
Offsets and lengths refer to decoded UTF-8 character positions, not raw byte offsets.
```

## Lyric Mapping Example

Example mapping from `99 Luftballons`:

```text
8.856s   pitch 49   "Hast"
9.228s   pitch 47   "Du"
9.414s   pitch 51   "et"
9.785s   pitch 47   "was"
10.343s  pitch 49   "Zeit"
```

Confirmed relationship:

```text
Lyric syllable -> lpsLyricMarker
lpsLyricMarker -> lpsMelodyMarker
lpsMelodyMarker -> timing / pitch
```

## Important RAM Areas

### Melody / Pitch

```text
0x407C....
```

Contains:

```text
lpsMelodyMarker objects
pitch/timing gameplay data
```

### Lyrics / Render Cache

```text
0x4102....
```

Contains:

```text
visible lyric text
render text
timing caches
```

### Runtime Note Nodes

```text
0x4153....
```

Contains:

```text
NoteNodes
companion objects
runtime render/gameplay data
```

## Proof of Concept

Confirmed working:

```text
Direct text replacement inside _Lyric.X360
```

The game displayed modified lyrics such as:

```text
bla bla bla
```

This indicates that simple text replacement works when the surrounding structure is preserved.

## Writer Development Notes

Recommended first approach:

```text
Template patching
```

Do:

```text
reuse an existing .X360 as a template
modify known fields only
keep object counts stable
avoid heap reallocation
avoid rebuilding unknown vectors unless necessary
```

Avoid initially:

```text
full IXB heap rebuild
changing object counts
large pointer restructuring
rewriting all vectors at once
```

## Next Technical Goals

Short-term:

```text
Patch only MelodyMarker timings and verify visible gameplay changes
Patch pitch values and verify pitch bar changes
Patch lyric text using structure-preserving replacement
Then combine timing + pitch + lyric mapping changes
```

Medium-term:

```text
Build stable parser
Build stable template patcher
Build UltraStar importer
Generate custom chart data
```

Long-term:

```text
Full UltraStar -> Lips conversion pipeline
GUI editor
Custom Lips DLC tooling
```

## Safety / Repository Notes

Do not commit or publish:

```text
original Lips DLC files
original audio/video files
Xbox 360 SDK binaries
RAM dumps
modified copyrighted song files
```

Recommended:

```text
private repo during research
public repo only with original code and documentation
no copyrighted assets
no SDK binaries
```
