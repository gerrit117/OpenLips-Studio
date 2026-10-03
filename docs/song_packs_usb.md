# Song packs and Xbox USB installation

## Studio workflow

- **File > Export > Export song pack** includes the current chart if it has
  notes. Add saved `.olp` projects, remove unwanted entries and name the pack.
  Projects must contain notes, lyrics, artist/title and local audio or video.
- Studio prepares each song's audio, 15-second preview from its first lyric, cover and optional
  video, generates fresh chart/lyric pairs and builds one named LIVE package.
- **Tools > Song preview** or the preview button in DLC export sets an
  automatic first-word start (default) or a manual start and duration. The
  default duration is 15 seconds. Settings are saved in `.olp` projects;
  older projects retain the automatic defaults. Audio and video use the same
  window, shortened naturally if the source ends. In pack export, select a
  song before editing its preview; those edits apply to that pack operation.
- Asset basenames are namespaced (`song00_audio.xWMA`, etc.) so songs never
  replace each other's files. Chart audio/movie names use the matching stems.
- **Tools > Copy DLC to Xbox USB drive** installs an exported package; the
  same command becomes available after a successful single-song/pack export.
- Select the attached Xbox Content drive. Nothing is copied automatically
  merely because a drive was connected.

This does not change the existing unsigned-package requirement: a suitably
modified console is needed. Copying to USB does not add a Microsoft signature.
The existing OG chart writer remains in use; this is not a new LS2 authoring
implementation.

## Manifest evidence

Nine original local manifest copies were inspected under
`Desktop/Lips/Songdateien` and `private/runtime/dlc-comparison`, representing
four distinct original manifests (duplicate copies are not independent evidence):

| Distinct manifest source | Songs | Videos |
| --- | ---: | ---: |
| I Don't Want to Wait | 1 | 0 |
| Everything About You | 1 | 1 |
| You've Lost That Lovin' | 1 | 0 |
| Musical song pack | 3 | 3 |

All four use `DLCContents/MusicIndices/MusicIndex` with the same basic asset
fields. The multi-song example shares `offerID`, `ChartContentID` and
`VideoContentID`, but has distinct `UintID`s. Its three video records have
`ID=<shared content ID>_000`, `_001`, `_002`. The generator follows those
observed pack conventions; single-song manifests are unchanged.

Frequency: multi-song relationships observed in 1/4 distinct manifests,
2 physical copies of that same pack. Confidence is **medium** for this
specific pack convention, **low** for treating it as universal across DLC.
No Avril-specific pack was available in this local set. Do not claim broad
retail validation based on the musical pack alone.

Studio allocates a 28-bit package identity with 24 random low bits and uses the upper song-ID
nibble as the slot, following the observed `0x0...`, `0x1...`, `0x2...` pattern.
The current UI allows 2..16 songs. This is an implementation limit, not proof
that every retail mode supports 16 songs. No installed-song-ID inventory query
exists yet. A pack name is the STFS display name, not a guessed extra XML tag.

The initial **110 MiB** authoring limit was not a Lips format limit. There is
an explicit counterexample: the available real musical pack is 337.07 MiB.
The initial limit has
been replaced with **2016 MiB** of assets, leaving headroom below 2 GiB for
package overhead. This remains a conservative native-backend limit, not proof
of the game's maximum pack size. Single-copy level-2 STFS hashing now passes
independent verification and byte-identical extraction across the 28,900-block
boundary and the second full level-1 table boundary (57,800/57,801 blocks).
The validator memory-maps the package and hashes bounded chunks rather than
allocating a complete in-memory copy. Dual-copy trees remain unsupported.

## Menu preview correction

The previous generator omitted both a separate preview WMV and the manifest's
`MusicVideo/PreviewVideoUri`. Four video entries from two distinct original
manifests have both preview video and NFT icon references (4/4). The locally
extracted NoH QueueMenu code reads `GetPreviewVideoUri()` and starts playback
at 0 seconds; an empty path selects a generic fallback. A separate menu branch
uses `GetPreviewIconUri()` for its static texture. Confidence is **high** that
the missing video reference prevented our own song preview from being loaded;
the corrected display on a console still requires testing.

Read-only preview-video inventory under `Desktop/Lips/Songdateien`:
10 physical files, 9 distinct SHA-256 contents. Files analyzed: With You,
Ey DJ, Hamma, 99 Luftballons (duplicate copy), Umbrella, Everything About You,
Any Dream Will Do, Don't Cry For Me Argentina, The Phantom Of The Opera.
All 9 distinct files have height 136 and WMA Pro audio. Widths: 240 in 6/9,
180 in 2/9, 184 in 1/9. Codecs: WMV3 in 6/9, VC-1 in 3/9. Durations range
from 15.079 to 15.515 seconds. These observations have **high** confidence
for this corpus, not universal requirements for all Lips releases.

The generator keeps its working VC-1/WMA Pro encoding path and adds a separate
240x136, 600 kbit/s video preview. Audio and video previews start at the
first note containing actual text (ignoring bare `~` continuation fragments),
run for up to 15 seconds and are not offset relative to each other. The
preview's own timeline starts at zero. Full-song media and chart timing are
unchanged. Preview lyric metadata contains fragments in that window, without
literal continuation tildes or repeated syllables.

`PreviewIconUri` is still absent: no unverified NFT serializer or copied
original NFT was added. Whether a particular UI branch also needs an NFT
thumbnail beyond the playable movie is an open console-test question. Songs
without source video continue to have audio previews only; this change does
not manufacture a full video or generic-video reference for them.

## USB storage and safeguards

For the modern visible Content layout, the installation path is:

```text
<drive>/Content/0000000000000000/4D530888/00000002/<header-content-ID>4D
```

Studio lists writable mounted FAT/FAT32 volumes with an existing Content
directory. It rechecks the selected volume when the copy starts. It never
formats drives, changes profiles, accesses raw sectors or replaces existing
packages. Non-directory entries, escaping junctions/symlinks and ambiguous
case-insensitive paths are rejected. Selection of the intended physical drive
remains the user's responsibility; a Content directory alone is not proof of
console configuration.

The package's STFS hashes are verified first. Free space is checked; copying
uses a unique temporary file, progress feedback, flush/fsync and SHA-256
read-back. Only a matching copy is renamed to its canonical filename, with
no-replace publication. Failures remove only this operation's temporary file.
Use the operating system's safe-eject operation before unplugging.

Older storage with `Xbox360/Data0000` files embeds FATX rather than exposing
the content directory directly. It is detected and refused, not edited.
References: [Free60 USB layout](https://free60.org/System-Software/Systems/FATX/)
and [the FAT32/legacy dashboard distinction](https://consolemods.org/wiki/Xbox_360:Files_and_Directories).
The user's stick was confirmed to expose `Content`, so this implementation
targets that layout. Raw FATX writing is deliberately outside this change.

## Validation

Committed tests use synthetic songs and temporary directories only. They
cover shared pack identities, unique song IDs and media names, mixed video/
audio-only packs, embedded chart media references, unchanged input projects,
USB no-overwrite, corrupt packages, insufficient space, read-back failure
cleanup, legacy refusal and the empty-drive UI state.

A local native smoke test produced a two-song/two-video package with 13
files including DLC.xml, independently verified all hashes and extracted it
byte-identically. It contained 2,714 blocks and 11,089,382 payload bytes.
All assets were generated synthetic media; the accepted user DLC was untouched.
Retail pack discovery/playback and copying to the user's physical USB stick
remain pending user validation. No game assets or generated packs are committed.

Local test suite: 442 passed, 8 skipped, 11 subtests passed. The optional
native single-song audio-only/video integration tests were enabled separately
and passed (3 tests), including repeated exports preserving earlier packages.
The frozen Windows app also passed `--smoke-dlc` (exit zero). The native
two-song pack was copied into a simulated Content USB directory and its entire
SHA-256 read-back matched the source. This is a filesystem simulation, not
physical USB hardware or console acceptance testing.

Follow-up preview/large-package tests: 444 passed, 14 skipped, 11 subtests in
the default suite. Enabling native DLC/media tests ran 29 focused tests with
no failures, including 28,900/28,901/29,070/57,800/57,801-block packages.
A synthetic source with a silent five-second intro confirms that preview
audio begins with the requested first-lyric signal, not silence; the linked
preview movie has 240x136 dimensions and approximately 15 seconds duration.
The previous local encoder binary was hash-checked and backed up before the
preview-capable encoder replaced it. No original game files were modified.

Manual preview settings and MIDI/LRC regressions: 453 tests passed, 15 skipped
and 11 subtests passed. The enabled native export subset passed all 36 tests,
including automatic 15-second and manual 10-second preview generation.
LRC assignment is an editable estimate from line/word anchors, not forced
alignment; it leaves MIDI note identities, times, durations and pitches intact.
The user's local HH MIDI/LRC pair was read without modification: 354 of 422
notes received text or continuation markers, and all musical fields matched.
Notes outside usable text windows remain untouched. The MIDI contains real
polyphony, so this assignment does not resolve simultaneous vocal voices.
