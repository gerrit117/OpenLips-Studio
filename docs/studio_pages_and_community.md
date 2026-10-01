# Phrase pages, projects and community direction

## Explicit OG page boundaries

The accepted fresh OG writer does not rely entirely on automatic text wrapping.
`build_owned_chart.py` emits `lpsPageBreakMarker` records in the Section sequence
and preserves individual note/lyric timings separately. UltraStar `-` line-break
records become `line_break_after` flags in the importer and internal note model.
Studio's phrase-end checkbox edits that same flag.

Current writer schedule:

- Initial page begins at `max(0, first_note.time - 0.8)`.
- After a flagged phrase end, the next page begins at
  `max(0, next_note.time - 0.8, min(previous_phrase_end, next_note.time))`.
- A final marker is emitted at `song_end - 1.0`.

These defaults apply only when no explicit `page_break_time` is supplied. Studio
can now set the exact next-page time on a phrase-ending note, and the fresh OG
writer emits it unchanged as a big-endian trigger float. It must not be later
than the next phrase's first note, and page times must remain chronological.
An early switch can truncate the previous visible phrase; it is not silently
clamped. The last note cannot request another page without a following phrase.

The previous importer preserved only the `-` boundary flag and discarded its
beat number. The new importer retains that beat as an exact page timestamp using
the same BPM/GAP conversion as notes. Standard absolute, one-value `-` lines are
supported; relative/multi-value forms warn and retain automatic page timing.
Imported syllables, durations, pitch and note starts are not redistributed.
See [UltraStar phrase specification](https://usdx.eu/format/).

Long/full, duet and LS2-specific rules remain outside this verified OG path.
Do not infer every original song's UI behavior from this one supported mode.

## Syllable duration

Each generated LyricMarker has the same trigger/length as its linked melody
marker. Studio's length control and right-edge drag change that duration; new
text is entered directly into the note's inline lyric field. A shorter duration
activates the fragment for less time, a longer one for more time. No independent
character-fill/easing-speed field has been verified, so the UI does not invent
one or claim pixel-identical reproduction of Lips' highlighting animation.

## Work-in-progress projects

`.olp` is versioned UTF-8 JSON containing metadata, note IDs/timing/pitch/text,
word/phrase flags, unassigned lyric draft, reference paths and preview offset.
Saving does not invoke the chart writer or require completed lyrics. Reference
audio/video remain external. Writes stage a temporary file, flush it and replace
the previous project atomically. Do not submit local reference paths to a community.

## Community preparation, not a launched service

A separate community/catalog API can later distribute chart/project revisions,
artist/title, duration, format version, contributor/license declarations and
media fingerprints for selecting the correct recording. Importers can consume
that API through the plugin contract without changing the core editor.

Never assume that charts containing lyrics are copyright-free just because audio
is absent. Lyrics can be protected literary works, and musical notation can also
raise rights questions. Require original/licensed/public-domain content or other
valid permission, moderation/reporting, takedown handling and a legal review
before launching. See [UrhG section 2](https://www.gesetze-im-internet.de/urhg/__2.html).

Use an explicit separate share/export format: strip local paths and identifiers,
exclude music/video/cover assets, validate lengths and payload types, require a
license declaration, and preview exactly what will be uploaded. No automatic
upload, accounts or community backend are implemented in the first desktop beta.
