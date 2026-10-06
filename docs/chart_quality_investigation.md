# UltraStar chart quality and Lips note scaling

Follow-up: [adjacent same-pitch words in original charts](native_same_pitch_notes.md).

## Investigation

Read-only investigation on 2026-10-03 after a real Xbox Number One Hits beta
test. Six local UltraStar files were imported, written through the owned
builder and read back using the schema-aware IXB graph reader. Original
Disturbia files were decompressed into an ignored analysis directory, never
modified in place. Native renderer bindings and callers were inspected in
Ghidra's read-only project mode. The private report contains paths, source
hashes, per-note comparisons and page statistics. No original lyrics, media,
charts, screenshots or decompiled game code accompany this public document.

## Timing and source authoring

| Local TXT | Notes | Median duration | Below 150 ms | Pages | Longest sung page |
| --- | ---: | ---: | ---: | ---: | ---: |
| Another Day In Paradise | 387 | 147 ms | 209 | 61 | 5.595 s |
| Merry Christmas | 440 | 191 ms | 75 | 60 | 4.278 s |
| Der Himmel brennt | 332 | 113 ms | 202 | 47 | 5.019 s |
| Abenteuerland | 538 | 229 ms | 52 | 114 | 3.467 s |
| Dirty Diana | 448 | 114 ms | 351 | 71 | 2.630 s |
| Disturbia | 687 | 180 ms | 287 | 96 | 4.501 s |

These measurements describe these particular files, not every version of each
song. Supported-note counts and MIDI pitches agree exactly after export.
Maximum start-time error is below 16 microseconds; length error is below 0.1
microseconds. The owned builder also validates Tone/octave fields. Structural
agreement is not proof of vocal accuracy or game playback.

Dirty Diana has more short notes than Der Himmel brennt and still played well
in the user's test. A universal minimum-duration rule is not justified.
Lengthening notes changes the required singing interval, not only appearance,
and can erase genuine pauses or create overlaps.

## Song-wide renderer scaling

The inspected Number One Hits renderer finds the **maximum sung page span over
the track**, caches it and uses it when calculating horizontal scale. Its
ordinary-marker spawn path passes the difference between end-time and
start-time coordinates to Lua, which applies it to the phrase marker's caps
and center. For the ordinary positive-span path, factors simplify to:

```text
regular note width = duration * display width / (page multiplier * maximum sung page span)
```

The multiplier normally starts at one; a special-page branch can select two.
This is a reconstruction of the inspected native path, not a universal pixel
promise for every edition, duet or marker type. Float rounding, caps and
screen layouts still affect screenshots. The maximum-span scan includes a
note starting exactly at an interval's end, so equality needs care.

**One long page can shrink bars throughout a song**, even on short pages.
The earlier explanation that only the current page determined width was
incomplete. The roughly 5-second maximum in Der Himmel brennt versus Dirty
Diana's 2.63 seconds explains their different visibility despite comparable
short-note lengths.

Existing intelligent reflow reduces Der Himmel brennt's reconstructed maximum
to 3.214 seconds without altering notes. Other factors unchanged, that
predicts roughly 1.56 times the bar width; an Xbox A/B test is still required.
Some long word/melisma groups cannot be divided safely: Disturbia's TXT keeps
a 4.501-second maximum after reflow. Reflow does not guarantee improvement.

## Original Disturbia

The normal melody contains 608 phrase markers and **11 hit markers**, with
472 lyric markers and 112 nonempty reconstructed pages. Its maximum sung page
is 2.455 seconds; median note length is 235 ms. The median gap between melody
events on the same page is about 5 ms, versus about 120 ms in the TXT.
Both distributions exclude page transitions, but they are not a matched-note
musical comparison. The TXT has 687 ordinary/golden notes, 96 pages
and different syllable/melisma authoring before conversion even starts.

`lpsHitMarker` is a distinct native class, with a dedicated sprite and vowel
field. Its spawn path does not pass a duration-derived bar width. Most sampled
hits last approximately 30 ms. Small ordinary phrase caps can look oval but
do not become hit markers. The owned exporter currently writes phrase markers,
not hits. Automatically turning all short syllables or UltraStar rap notes
into hits would be speculative: sampled native hits still contain pitch data
and their grading semantics have not been verified for owned charts.

## UltraStar semantics and limitations

The [official v1 specification](https://github.com/UltraStar-Deluxe/format/blob/main/The%20UltraStar%20File%20Format%20%28v1%29.md)
defines the legacy timing unit as `60 / (4 * BPM)` seconds; GAP is milliseconds
and pitch is a semitone offset from C4. These conversions match our importer.
Minus records end phrases, not individual notes. Regular/golden notes share
timing semantics; freestyle and rap have different scoring rules. Word
separating spaces can precede or follow a syllable.

The [UltraStar Deluxe renderer](https://github.com/UltraStar-Deluxe/USDX/blob/master/src/base/UDraw.pas)
scales the current line to available width, unlike Lips' song-wide
normalization. A TXT can look comfortable there and compressed in Lips without
a note-timing conversion bug.

Studio normalizes golden notes and warns when discarding freestyle/rap notes.
Another Day In Paradise has eight discarded freestyle events; Dirty Diana
has 36. None of these bad examples contains rap events. Independent duet
voices, legacy relative timing, leading-space-only word boundaries and the
unpublished v2 timing conventions are not fully supported. These are real
coverage gaps, but do not explain the supplied Himmel file's short normal notes.

## SingStar provenance

Abenteuerland appears in the contemporary Sony-supplied
[SingStar The Dome track list](https://www.games.ch/2284-singstar-the-dome/news/singstar-the-dome-erste-bilder-und-alle-lieder-auf-einen-blick-vic/).
The local TXT names that edition too. This supports its claimed provenance,
not proof that this specific TXT is an unchanged commercial extraction.
Dirty Diana's file names a community creator and no SingStar edition. Searches
of PS2, PS3 and downloadable-song lists did not confirm a SingStar release;
that is not an exhaustive proof about every regional or historical catalog.

## Editing and hardware verification

Single-song imports retain source page breaks. Since 0.4.0, batch imports and
Song Pack export optimize layouts automatically; explicit manual layouts are
retained. Intelligent reflow in the editor and manual recording are undoable
operations. **Record page switches** arms the keyboard
toolbar button. Space starts playback when paused and records a cut while
playing; Esc disarms. A press inside a silent gap retains its timing. A press
inside a word snaps to the nearest complete-word boundary, keeping syllables,
melismas and overlapping vocal events together. Text fields still accept
spaces. **Clear page switches** provides a clean layout; arming does not erase
existing cuts. Project saves and native exports retain recorded timing without
changing note pitch, start or duration.

Private A/B projects preserve source pages and intelligent reflow separately.
Export them with identical media and independent generated song IDs, then
compare identical passages on Xbox. Check singing timing as well as width.
Do not infer game acceptance from structural round-trip tests. No game files
or installed DLCs were changed during this study.
