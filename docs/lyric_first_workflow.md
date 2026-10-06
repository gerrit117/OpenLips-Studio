# Lyric-first song creation

Available in OpenLips Studio 0.4.0 Beta. This workflow is local and needs no
AI model, GPU or external service. It creates lyric timing, not an automatically
transcribed melody.

## Start with LRC

1. Choose **Create song > LRC only** and select the LRC file.
2. Optionally add reference audio/video and a cover; these can also be added later.
3. Review the grey blocks in the editor. Their pitches are **unassigned**.
4. Assign pitches, correct lengths and split blocks where needed. Save unfinished
   work as an `.olp` project.

Importing LRC into an empty editor also creates a lyric-first draft. With an
existing melody, the existing lyric review/assignment workflow remains available.

Ordinary LRC contains line starts, not exact word or syllable lengths. Studio
creates one provisional block per line, ending at the next timestamp. Enhanced
LRC supplies fragment starts where present. These intervals can still include
silence. A final empty timestamp bounds the last fragment; without a bound,
its provisional duration is two seconds. Check and correct it against the media.

Right-click a block to split it at the pointer, or divide a line into words.
**Split into words is an equal-duration estimate**, not acoustic alignment.
Splitting a word into several pitches gives the later segment a melisma
continuation (`~`) instead of repeating its lyric. The game export handles
that continuation; it is not printed as another word.

Select a block and assign a MIDI pitch in the inspector, use Up/Down, or drag
it vertically. Its grey appearance disappears once a pitch is assigned.
Horizontal moves and resizing do not invent pitches. Ctrl-click selects
multiple notes; merging requires compatible pitches and remains an explicit
action, not a side effect of page optimization.

## Record timing from plain lyrics

1. Choose **From scratch > Timing Assistant**, or open it from **Tools**.
2. Add reference audio/video and paste lyrics. Default mode is one tap per word.
   For syllables, divide them explicitly with `|` and choose syllable mode.
   Text newlines retain phrase grouping.
3. Enable recording. While playback runs, press **Space** at each next fragment.
   The next fragment and progress are displayed. Holding Space does not add
   repeated events.
4. After the final prepared fragment, press Space once more at its end, or stop
   recording there. Each new onset provisionally ends the previous block;
   shorten it manually if the singer leaves a gap before the next word.
5. Turn recording off and listen back with **timing ticks** enabled. Edit starts,
   lengths and text in the table. Seek or slow playback when checking a passage.
6. To redo a passage, select its row and choose **Re-record from selection**.
   Later entries are removed and recording restarts just before that fragment.
   Undo/redo restores recorded timing. Accept to bring the draft into the editor.

You can also record blank onsets and paste the text afterwards. They are assigned
in order without changing the recorded times. Partial recording is allowed for
an unfinished project; ensure the whole lyric has been timed before export.
Opening the assistant disarms page-switch recording, since both use Space.
Normal text entry accepts spaces when recording is off. Existing notes are
replaced only after confirmation and acceptance; cancelling keeps the original
project unchanged.

## Review and export

Ticks and reference audio have independent volume sliders. A tick verifies the
onset, not pitch or sung duration. In the main editor, optional note tones help
check the melody; unassigned blocks do not produce a placeholder pitch.

**Project save** keeps all draft data in `.olp`, including unassigned pitches.
**Tools > Export LRC** writes enhanced LRC with word/fragment timestamps.
Melisma continuations are not duplicated as words. **File > Export > Advanced >
MIDI** writes the melody once pitches are assigned. Both interchange exports
use `media_time = chart_time + reference_offset`; they reject negative media
timestamps. LRC does not contain pitch. Keep `.olp` as the editable master.

Community/chart/DLC export rejects unassigned pitches instead of silently
converting grey blocks to C4. Normal validation for timing, lyrics and overlaps
still applies. These workflows do not guarantee that a provisional word span
matches the duration of a sung vowel.

## Automatic pages

UltraStar batch import automatically prepares readable pages before saving
projects or opening Song Pack export. Song packs enable the same optimization
by default; the export checkbox can disable it. Explicitly marked manual
layouts are preserved. A single UltraStar import keeps its source breaks until
the user chooses Intelligent Page Breaks or edits/records a manual layout.

Optimization operates on a copy for export. It changes page boundaries, not
note starts, durations, pitches or lyric fragments. It uses the existing
whole-word, pause and phrase rules documented in
[the corpus study](lyric_page_corpus.md), not a new AI model or arbitrary
stretching of short notes.
