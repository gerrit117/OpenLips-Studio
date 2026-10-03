# Original lyric pages and note widths

## Scope and reproducibility

Measured on 2026-10-03, without changing source files. All 59 charts and 60
lyric samples under `private/samples` were inventoried, alongside 40 chart
pairs from the OG 2008 backup and 112 from the extracted Number One Hits
Levels directory. That is 211 physical chart/lyric pairs and 212 lyric files
available. One lyric sample, Don't Cry For Me Argentina, has no matching
chart in these roots and cannot contribute page counts.

SHA-256 of both files deduplicates copies: 130 distinct pairs, 128 parsed.
ABC's selected text resource fails strict UTF-8 decoding; Irreplaceable's
chart uses an unsupported compressed container. Neither is silently guessed.
OG contributes 38/40 parsed pairs, local samples 57/59, NoH 110/112;
these overlapping subgroup counts must not be summed as independent songs.
This is the available local corpus, not every commercial DLC ever released.

The private manifest `private/outputs/lyric-pages-corpus-20261003-width.json`
lists **every analyzed absolute chart and lyric path**, hashes, duplicate
copies, per-track page measurements, failures and unpaired lyrics.
No original lyrics or game files are included in this public document.

`python -m tools.analyze_lyric_pages --corpus label=directory --out report.json`
repeats the read-only measurement; use multiple `--corpus` arguments.
The local lyric fallback directory defaults to `private/samples/lyrics`.

## Method and limitations

Page intervals come from owned `lpsPageBreakMarker` records in the Section
sequence, not guessed newlines. Normal Melody/Lyric tracks are measured
separately from Duet tracks. Notes are Melody-marker-derived records;
characters are decoded Unicode characters, including normalized inter-word
spaces, reconstructed from lyric word-data spans. Consecutive identical
spans are counted once to avoid repeating a melisma's displayed word.
This is reconstructed visible content, not a screenshot or pixel-width test.

Normal tracks: 128, 11,397 nonempty measured pages, 52,900 notes.
Duet tracks: 116, 8,074 pages, measured independently (not extra unique songs).
Young Folks has 21 null lyric-to-melody links. Ladies Love Country Boys has
46 null links and 9 lyric-only intervals excluded from note/page statistics.
Other linked lyric markers have no page-assignment disagreement with their
melody link. These two files reduce confidence in their individual results;
the anomalies are retained, not treated as a general format requirement.

Section page markers use only track index 0 in 123/128 parsed files, only 1
in 2/128, and both in 3/128. Statistics use Section timing boundaries;
exact native track-index semantics for the five exceptions remain unverified.

## Observed normal pages

| Metric | Median | 95th percentile | Maximum | Confidence |
| --- | ---: | ---: | ---: | --- |
| Visible characters | 16 | 30 | 48 | high for reconstruction; medium for exact rendering |
| Notes | 5 | 8 | 14 | high |
| Words | 4 | 8 | 14 | medium: reconstructed spacing |
| First-note to last-note end | 1.447 s | 2.492 s | 5.089 s | high |
| Interval between page markers | 1.848 s | 3.692 s | 10.561 s | high |
| Individual note length | 0.235 s | 0.709 s | 4.682 s | high |

30 or fewer characters: **10,932/11,397 pages**, with exceptions in 69/128
files. Eight or fewer notes: **10,908/11,397**, exceptions in 68/128 files.
Three seconds or less of note span: **11,298/11,397**, exceptions in 16/128.
No measured normal page exceeds 16 notes or 8 seconds of note span.
Therefore our previous 42/16/8 defaults were permissive, not representative.
Duet medians are 15 characters, 4 notes and 1.402 seconds; the same 30/8
95th-percentile envelope supports the recommendation independently.

## When cuts happen

Explicit Section page markers are present in **128/128 parsed pairs** (high).
Among **11,269 normal-page transitions with subsequent notes**:

| Pattern | Occurrence | Confidence |
| --- | ---: | --- |
| Final lyric marker has end-of-word flag | 11,080/11,269 | high: common, not invariant |
| Cut at/after preceding page's last note end (0.1 ms tolerance) | 11,258/11,269 | high |
| Cut within 100 ms after last note end | 6,045/11,269 | high: common, not invariant |
| Text resource has a newline after last span | 3,890/11,269 | medium |

The median delay after the previous last note is about 91 ms; the median
lead before the new page's first note is about 124 ms. There is no single
universal lead time. Text newlines alone are not enough to recover pages.
Duet transitions end a word in 7,958/7,958 measured cases, but this must not
be generalized to every normal-song transition. Eleven normal transitions
occur before the preceding final note ends; copying that rare behavior into
a general writer is not justified.

## Why pills can look tiny

Original notes are not uniformly long: **3,407/52,900** are under 100 ms,
present in **52/128 files**; **8,499/52,900** are under 150 ms, in **106/128**.
Their existence is high-confidence. An imported short note is not necessarily
a format error or something that should automatically be lengthened.

The OG and NoH ChartRenderer Lua both position notes through
`GetXFromTiming` and apply a native-supplied `displayLength` using
`SetTotalWidthDirect`. The actual time-to-width calculation is native, so
the following is an inference, not a verified pixel formula: putting a
235 ms note into an 8-second time window gives it much less room than a
roughly 2-second window. Shorter pages address crowding without changing
pitch, note duration or scoring timing. The source of a specific user's
tiny pills still requires the exported pair or an Xbox before/after test.

Both inspected LyricRenderer scripts measure text width, use a safe width
of 1090 coordinate units and clamp scaling to no smaller than 0.7.
Confidence: high for those **2/2 scripts**, medium beyond those versions.
This is a width rule, not a 30-character file-format limit; unusually wide
words and duet text can still overflow despite a character target.

## Studio policy

The optional, undoable page optimizer now defaults to **30 characters,
8 notes and 3 seconds of note span**. Confidence: medium as a practical
starting preset, not a hard restriction. It splits at complete word groups,
keeps continuation notes together and preserves existing breaks. A long
indivisible word/melisma is reported rather than shortened. Imported
UltraStar pages are unchanged until the user explicitly requests optimization.
The writer's existing automatic switch timing is retained; this analysis
does not justify changing every song to a constant 91 ms delay.

No pitches or note durations have been changed by this work. Actual Xbox
text fit and note-width improvement still need a controlled playback check.
