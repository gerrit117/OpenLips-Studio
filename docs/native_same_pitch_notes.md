# Adjacent same-pitch words in native Lips charts

## Scope

Read-only follow-up on 2026-10-06. The previous hash-deduplicated corpus
provides 128 parseable chart/lyric pairs; decompressed Disturbia adds one.
Normal Melody/Lyric tracks were inspected, not summed with duet variants.
The study covers 53,520 melody events across 129 distinct pairs, including
38 pairs present in the original 2008 extraction. This is the available
local corpus, not every published DLC.

Each lyric event was linked through `m_pMelodyMarker`; its text spans and
end-of-word flag were read from schema-described structures. A same-pitch
word transition requires two adjacent ordinary phrase markers on the same
page, matching Tone/octave pitch, visible text on both and an end-of-word
flag on the earlier event. Hit markers, unlinked text and page transitions
are not treated as ordinary same-pitch word pairs. Word flags and written
spacing are imperfect linguistic evidence; the music was not automatically
transcribed or acoustically verified.

Licensed fragments, full event timings and opaque word-data bytes remain
in the ignored private report. They are not part of this document.

## Separate events, nearly adjoining bars

127 of 129 tracks contain qualifying same-pitch word transitions: 11,562
pairs in total. Of these, **9,602 (83.0%) have nonnegative gaps no larger than
10 ms**, allowing 0.1 ms of float tolerance. The OG subgroup contains 3,431
pairs, of which 2,578 (75.1%) meet that threshold.

| Original chart | Same-pitch word pairs | Median gap | Median earlier-note duration |
| --- | ---: | ---: | ---: |
| Amazing | 59 | 5.2 ms | 183 ms |
| Another One Bites the Dust | 162 | 5.7 ms | 130 ms |
| Bleeding Love | 114 | 6.0 ms | see private report |
| Call Me | 31 | 4.4 ms | see private report |
| Every Little Thing She Does Is | 106 | 3.8 ms | 179 ms |
| Disturbia | 141 | 5.0 ms | 235 ms |

These are genuinely separate melody events with separate lyric assignments,
not a single long note containing the whole passage. OG and NoH Lua each
clone a phrase-marker sprite for the supplied marker, set its width from
`displayLength` and position it using that marker's time and pitch. The
inspected NoH native regular-marker path computes width from its own start
and end coordinates. No general same-pitch merging rule was found in these
paths or the inspected charts.

Small gaps plus the song-wide scaling described in the
[earlier investigation](chart_quality_investigation.md) plausibly make these
separate bars appear more continuous. Exact cap overlap and the perceptual
effect need matched screenshots; the data alone is not a pixel test.

This is not exclusive to matching pitches: 16,825 of 20,191 qualifying
different-pitch word transitions (83.3%) also have gaps at most 10 ms.
The observation is principally about native chart authoring, not proof of
a special renderer feature for identical pitches.

## Comparison with local UltraStar sources

Applying the corresponding same-page, same-pitch word-pair filter to the
six supplied TXT imports gives:

| TXT | Pairs | Median gap | Median earlier-note duration |
| --- | ---: | ---: | ---: |
| Another Day In Paradise | 22 | 73.6 ms | 184 ms |
| Merry Christmas | 134 | 114.6 ms | 153 ms |
| Der Himmel brennt | 98 | 112.8 ms | 113 ms |
| Abenteuerland | 83 | 51.0 ms | 153 ms |
| Dirty Diana | 75 | 114.4 ms | 114 ms |
| Disturbia | 138 | 120.0 ms | 120 ms |

These are different arrangements/charts, not aligned acoustic comparisons.
Dirty Diana still played well in the user's beta test despite its gaps;
gap size is therefore not the only quality factor. In Himmel's qualifying
pairs the median gap is approximately as long as the preceding note. That
can produce a visibly disconnected pattern even after page reflow.

## Multi-fragment exceptions

Five events across four tracks have multiple word-data entries or multiple
lyric markers linked to a melody event. One entry is empty and two cases
are syllable/punctuation combinations. The two multiple-lyric cases both
use the same lyric start and duration, not separately timed words spread
across a sustained note. Including internal whitespace yields 29 candidates
in seven tracks, many of them punctuation spacing or written elisions.
These exceptions do not establish a general timed-multiword sustained-bar
mechanism, nor a rule that identical pitches should be merged.

## Consequences for Studio

### Is visual width independent of note duration?

A follow-up source check confirms that ordinary bars do not have an
independent per-word traversal speed in the inspected paths. Both OG and NoH
`PhraseFill.Growing:EvalState` calculate progress using the renderer's current
elapsed-time coordinate minus the fill start coordinate, bounded by the end
coordinate. The inspected NoH native regular-marker spawn calculates the
background bar width using its marker start and start-plus-length coordinates.
Both operations use the same time-to-position mapping.

In clean-room notation, for a fixed display context with positive scale k:

```text
X(t) = origin_x + k * (t - origin_time)
background width = X(note_start + duration) - X(note_start) = k * duration
growing fill = clamp(X(now) - X(fill_start), 0, X(note_end) - X(fill_start))
```

Within that context the time-driven horizontal speed is k, rather than a
separately authored speed for each note. Page/layout scale can change k, but
then it changes bar width and traversal together. Enlarging bars through page
reflow therefore preserves their original duration: the time-to-position
scale changes, not the musical event length. Lengthening a chart note instead
changes its end time; it is not merely a cosmetic width instruction.

Caps, short-marker clipping and support-fill adjustments for slightly late
singing affect appearances near boundaries; hit markers have a different
renderer. These exceptions do not establish independent regular-bar timing.
The fill is also initiated by singing/grading events, not a guarantee that
every note is automatically painted from its first instant.

Text highlighting is separate. Both inspected LyricRenderer scripts pass a
wipe start/end interval to a text sprite. For a linked melody marker that
interval defaults to the melody marker's start and length; the lyric marker's
own timing is used as a fallback when no melody marker is provided. Thus
different text widths can have different visible wipe speeds. A separately
stored lyric length is not evidence that a long linked melody bar can be
given a short independent singing interval.

An independently widened short bar with a correspondingly rescaled fill could
be implemented in a renderer, but is not a demonstrated chart-only export
feature of these original game paths. Maintaining positions, note spacing,
text timing and grading would need further work if changing the renderer.

### Safe editing policy

- Keep separately timed words and their lyric onset information. Automatically
  merging every matching-pitch run would erase articulation and text timing.
- Existing explicit same-pitch merge remains useful for truly artificial
  splits that a user has checked against audio.
- An optional, undoable duration adjustment could test reducing short gaps
  within a page while retaining separate notes and lyrics. Pitch equality
  alone cannot decide whether audio contains a real pause. Extending durations
  changes scoring windows and needs playback review; no automatic change was
  made to imported charts in this study.
- A game-style page preview should show both global scaling and actual gaps,
  rather than suggesting note count alone determines visual quality.

No original songs, existing comparison projects or application behavior were
changed during this follow-up. A source authoring recommendation is not a
new Xbox-verified export feature.
