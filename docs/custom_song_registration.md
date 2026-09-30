# Independent OG song registration

## Working result and preserved checkpoints

A fresh 780-note chart and lyric pair, built from the replacement UltraStar
reference, loads from its own `Levels/Custom/...` paths with generated media.
The user confirmed playback. Computer Use subsequently verified the list entry:
correct title, artist, year and genre, 41 songs rather than 40. No existing song
was replaced. The isolated original test slot was restored and hash-checked.
Cover art is currently the game's fallback; separate preview audio is absent.

Both the earlier successful slot test and this independent registration are
checkpointed privately, including files, config, runtime log and SHA-256 hashes.
Never commit those media, game databases or source lyrics.

## Disc catalog is a diagnostic path, not final installation

`tools/register_og_song.py` creates a new copy of the OG 41-column `MusicDB`.
It inserts one new identity and relative asset paths, without cloning another
song row. It requires the measured disc schema/family, checks identity
collisions, preserves original rows and other tables, performs SQLite integrity
validation, and refuses existing output paths. Publishing uses a same-directory
temporary file and a no-clobber hard link. Synthetic tests cover these rules.

The constants TitleID=0x4D530888, DiscIndex=3, Source=0, AudioState=2 and
ChartState=2 occur in 40/40 untouched OG disc rows (high confidence for that
catalog). LeaderBoardID=0 is chosen for the custom entry rather than reusing an
official song's online identity; online behavior is not tested.

An existing profile did not import the newly added disc row. Removing only the
emulator cache was insufficient. A fresh offline profile did import it and
display 41 songs. The old profile remains intact; it was not reset or deleted.
Do not require users to create new profiles or delete saves as an installation
procedure. The final builder must register new songs through DLC discovery.

## Timing and short notes

Replacement reference: BPM=384, GAP=15940 ms, 780 notes; the prior lyrics-video
reference had GAP=10180 ms and 770 notes. The replacement identifies the same
official video as the supplied media. Formula remains:

```text
time = GAP_ms / 1000 + beat * 60 / (BPM * 4)
length = duration_ticks * 60 / (BPM * 4)
```

The user observes approximately 1-2 seconds of early text. A separate controlled
build adds `--note-offset 1.5`, delaying notes, their linked lyric markers and
generated page breaks together. It does not shift media/tempo start or stretch
notes; CLI requires an explicit song duration to keep media/end timing fixed.
This candidate loads from the independent entry; Computer Use verified active
notes, lyric pages and video, and native clock progression. The user reports
that +1.5 s is too late. It is a rejected alignment candidate, not a new
default and not evidence of an IXB format failure. Preserve the zero-offset
working pair for comparison.

Imported note lengths: minimum 0.078125 s, median 0.117188 s, maximum 0.742188 s.
Thus short bars already follow source durations; removing the formula's factor
of four would also multiply song timing and is not a justified fix. Optional
gap filling/legato would be a separate, explicit chart transformation, bounded
by the next note and phrase boundary, not an importer correction.

## DLC corpus: next installation target

Read-only inspection covered all four extracted `DLC.xml` reference manifests
under the local `Songdateien/DLCs` tree: `every`, `I Dont Want to wait`,
`song pack`, and `you lost`; six MusicIndex entries and four MusicVideo entries.
The separately edited root manifest was excluded from reference distributions.
These are small-corpus observations, not a universal specification.

| Pattern | Occurrence | Confidence |
|---|---:|---|
| DLCContents / MusicIndices / MusicIndex | 4/4 manifests | Medium |
| Identity, metadata, ChartUri, AudioUri, LyricUri, jacket/preview audio fields | 6/6 entries | Medium |
| offerID, UintID, ChartContentID, VideoContentID | 6/6 entries | Medium |
| Separate MusicVideos section | 2/4 manifests | Medium |
| Video/preview URI and VideoContentID fields | 4/4 video entries | Medium |
| LicenseBits element | 3/4 manifests | Medium; not always present |
| MusicVideo.ChartID | 1/4 video entries | Low; single reference |
| MusicVideo.ID instead of ChartID | 3/4 video entries, one package | Low; package-specific |

Do not infer that renaming loose files or writing DLC.xml alone constitutes a
valid DLC package. Next controlled work must resolve the existing OG DLC XML
reader's identity/link conventions, produce coherent new IDs and resource
paths, and test content discovery with an already existing profile. Preserve
the working chart and codec pipeline while isolating packaging.

Local Xenia Canary source supports both container and directory-backed content
packages. Directory packages need separate content metadata headers; its
`ContentPackageDirectory::ReadContentHeaderFile` accepts specific header sizes,
and ContentManager enumerates by profile/title/content type. An extracted
Xenia staging directory is not an Xbox-installable signed STFS package.
Hardware packaging/acceptance and independently encoded DLC audio/previews
remain unverified. In particular, the tested OG movie audio path must not be
assumed equivalent to a DLC xWMA path without a controlled test.

The compact-family reference chart in `you lost` contains an ixAudioMarker
whose resource name is an original disc-style `Levels/Intl/..._GV` name,
whereas its manifest names a package-local xWMA. Therefore a DLC chart's
embedded audio URI must not be guessed solely by concatenating the package
filename. This is one-file evidence (low confidence); inspect all available
charts and the runtime music-index override before choosing the synthetic
DLC resource binding. No rewrite of the accepted chart or lyric ownership
graph is warranted by this observation.

## Reproduction commands

Use private output paths and your own source files/catalog. This is a modular
debug pipeline, not the final one-command authoring interface:

```text
py tools/import_ultrastar.py input.txt --out private/song.json
py tools/build_owned_chart.py private/song.json --name NewSong --audio-name Levels/Custom/NewSong/NewSong --movie-name Assets/InGame/Levels/Custom/NewSong/NewSong --song-duration 263.3 --out-dir private/new-chart
py tools/normalize_og_asf.py private/encoded.wmv --out private/accepted-header.wmv
py tools/register_og_song.py private/original-MusicDB --out private/new-MusicDB --title "New Song" --artist "Artist" --asset-stem Levels/Custom/NewSong/NewSong --uint-id 0x19001 --song-id DVD4D530888000_9001
```

Timing parameters in the working runtime checkpoint are recorded privately;
defaults in this illustrative command are not a synchronization claim.
