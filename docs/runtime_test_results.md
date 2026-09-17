# Runtime Test Results

This document records sanitized observations from tests on a real console. It
contains no song titles, lyrics, private paths, or original game data.

## Confirmed Result: Same-Length Lyric Edit

Status: successful on real Xbox 360 hardware.

Facts:

- A Lips-1 plain-IXB lyric resource was copied and patched without modifying the
  original file.
- Exactly one visible ASCII word was replaced with another four-byte ASCII word
  (`4 -> 4`).
- The matching chart file was not changed.
- File size, IXB header, class table, `NumOfElements`, section bounds, marker
  counts, payload length, and chart-worddata coverage remained unchanged.
- The reported payload-length field, hash-like field, and pointer-like fields
  were left byte-identical.
- The game and song loaded, and the replacement text was visibly rendered on
  the console.

This proves that, for the tested Lips-1 template and runtime path, a same-length
in-place change to the selected visible lyric payload does not require changing
the currently reported hash-like, length, or pointer fields.

It does not prove that those fields are unused for every file family or that a
different-length edit is accepted. Duplicate song resources and
game-version-specific load paths must also be ruled out when a locally valid
patch is not visible at runtime.

## Confirmed Result: Full Visible Payload Replacement

Status: successful on real Xbox 360 hardware.

Runtime Test 2 used a different Lips-1 plain-IXB template with 100%
chart-worddata coverage. The complete visible lyric content was replaced with
synthetic `TEST` patterns and adjusted same-length words. The console loaded the
song and displayed the replacement words correctly.

The test preserved:

- every character and byte position;
- whitespace, line breaks, punctuation, prefix/BOM, and trailing padding;
- chart `LyricWordData` offsets and lengths;
- payload length and file size;
- the hash-like field and all pointer fields;
- the complete IXB structure and object graph.

This proves that a Lips-1 template can carry entirely new visible lyric content
without rebuilding IXB metadata or changing the chart, provided the decoded
text layout and every existing `LyricWordData` range remain position-compatible.
It also proves that the unchanged hash-like field does not reject a large
same-capacity content change on the tested runtime path.

It does not yet prove:

- that visible text length or payload capacity can change;
- that chart `LyricWordData` offsets and lengths can be changed safely;
- that marker records can be added or removed;
- that the same behavior applies to later/DLC, LS2, or compressed files.

### Attempt 1 Observation

The first full-payload candidate did not reach lyric rendering. The console
reported a media/disc-read error for that song; its cover and preview audio were
also unavailable, while the game itself remained running. Other original files
were still present. This is recorded as a song-specific, inconclusive load
failure rather than proof that the template-preserving payload edit was
rejected.

The prepared Test 2 artifact was therefore replaced with a different Lips-1
plain-IXB song. That second attempt is the successful full-payload result
documented above. The previous private artifact remains archived locally for
comparison.

## Recommended Next Runtime Boundary

The next meaningful test should combine a different-length visible lyric with
updates to existing chart `LyricWordData.text_offset` and `text_length` fields.
It should stay within the template's existing payload capacity, preserve the
total payload length and file size with the observed padding, and keep marker
count, timing, object graph, hash-like field, and pointers unchanged.

This isolates chart-to-text mapping from container resizing. Growing beyond the
existing capacity or changing marker count should remain a later phase.
