# Studio pitch and melisma export correction

## Retail control

On 2026-10-02 the user reported that an exported DLC is recognized on a real
Xbox 360 running Lips Number One Hits. This confirms recognition of that
specific package, not every DLC or complete correctness of scoring, pitch,
timing or lyric presentation. Its absence from Xenia remains a separate issue.

## Pitch inversion

Studio stores MIDI pitch (`UltraStar pitch + 60`). The owned-chart writer
previously passed that MIDI value into the legacy descending file-index
converter. This produced an inverted contour: a higher Studio note generated
a lower Lips Tone. Screenshots of the same phrases are consistent with this.

A read-only scan of all 59 chart files under `private/samples/charts` yielded
markers in 58 files, 40,789 markers total. All extracted markers satisfied:

```text
file_index + fIdx + 12 * octave = 127
```

The remaining file yielded no markers and supplies no pitch evidence. This
distribution covers extractor-produced records, not a claim that every object
in every compressed/unknown variant was decoded. The original ChartPreview
Lua's active Oboe entries independently associate MIDI-like numbers 49, 52,
55, 61, 73 with tone classes 1, 4, 7, 1, 1 and octave counters 4, 4, 4, 5, 6.
The entry named 97/A#6 is inconsistent and was not used as a reference.
No copyrighted script or sample data is included in committed tests.

The owned writer now explicitly converts:

```text
file_index = 127 - MIDI
fIdx = MIDI % 12
octave = MIDI // 12
```

The schema calls the historical `raw_pitch` field `m_iTrackIndex`. Do not
equate that field directly with MIDI. The legacy raw-index patch helper remains
unchanged; the fix applies at the MIDI-to-file boundary in the owned writer.
The matching LyricMarker uses the same converted index.

## Melisma text

The supplied TXT contains bare `~` continuations and fragments such as `~t`.
Those are not intended as visible tildes. The owned writer removes the tilde
from mixed fragments and emits no additional LyricMarker for bare continuations.
The final continuation's word-ending flag is carried to the preceding syllable.
Notes,
pitch changes, timing, word endings and page transitions remain intact.
An orphan continuation at song/phrase start is refused rather than silently
assigned to an unrelated word. Studio/project source text is not modified.

### Failed shared-range approach and correction

The first tilde-removal test shared the preceding WordData range with each
continuation. The user's retail Xbox test showed repeated words despite the
payload containing each fragment only once: Lips builds visible lyrics from
the individual LyricMarkers. Sharing a range does not suppress repetition.

All 59 local chart files were inspected; 58 supported graphs were usable.
MelodyMarkers without a referencing LyricMarker occur in 55/58 supported
files (including Amazing: 883 melody, 828 lyric, 55 unlinked melodies).
Confidence is high that a lyric entry for every melody is not required;
not every unlinked record is necessarily a melisma, so that interpretation
alone has medium confidence. Only three zero-length WordData entries were
found, all in one file: this rare pattern was not used as a general rule.
The writer keeps bare continuations in the Melody sequence without creating
duplicate Lyric sequence entries. Mixed suffixes such as `~t` still emit `t`.
Intentional repeated words are preserved. Retail validation of this updated
continuation behavior remains pending.

## Durations and validation

Real-file smoke import and fresh pair generation for the user's local TXT
produced 361 melody records. Durations: minimum 0.037898 s, median 0.227388 s,
maximum 2.084386 s.
The corrected continuation export produces 314 lyric records for those same
361 melody records: 47 bare continuations retain their notes without repeating
the preceding text.
The writer serializes the imported durations as float32;
it does not shorten or automatically stretch them. Extremely short source
notes therefore remain short. Notes of different pitch must not be merged
merely to make bars longer. Same-pitch manual merging remains available in
Studio. Actual Xbox presentation after this correction still needs testing.

Validation now reads every generated melody back, including continuations, and checks time,
length, file index, tone and octave, as well as each resolved lyric range.
Synthetic regressions cover ascending MIDI conversion across 24..84, descending
phrase contours, preserved durations, mixed/bare melisma and orphan rejection.
Full suite: 432 passed, 8 skipped, 11 subtests passed. Generated real-song
outputs remain private; no samples, media or screenshots are committed.

The local frozen Windows build also passed `--smoke-dlc` (exit zero): generated
synthetic media, bundled conversion, 17-second full audio, 15-second preview,
integrated STFS packaging and extraction verification. This is not an Xbox
playback test. A new private local installer is supplied for user validation;
no GitHub push or release was performed.

The updated melisma-fix frozen build also passed `--smoke-dlc` with exit zero.
Local build and generated comparison files are stored separately from the
previous pitch-fix build; original samples and user project files are unchanged.
