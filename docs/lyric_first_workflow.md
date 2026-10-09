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

In the 0.4.6 Beta 2 local build, either edge has a horizontal resize cursor:
drag the left edge to change the start while keeping the end, or the right edge
to change the end while keeping the start. Edges stop at neighboring notes;
the Grid checkbox controls snapping. Delete selected blocks with Delete or
the chart context menu. All of these changes can be undone.

Choose a major/minor key beside BPM to highlight its scale notes in the chart.
The selected note's **Scale notes** list offers pitches in the visible vocal
register, within Lips' supported range. This is a guide, not a restriction:
chromatic notes remain available through MIDI pitch entry, dragging and arrows.
The minor guide is natural minor. A key does not determine the singer's octave
or guarantee a correct melody; no automatic audio key detection is implied.

**Add melisma here** in the context menu splits a word into linked segments.
The continuation keeps the same word without repeating its text in game;
change its pitch with arrows or the inspector. A dashed connector shows the
relationship and the inspector displays the shared word. Deleting its first
segment retains that word on a surviving continuation.

To repair text alignment partway through a song, select the first affected note,
then mark the corresponding word or syllable in the right-hand lyric text and
choose **Assign from selection**. Assignment starts at both anchors, not at the
beginning of the text. Earlier notes, musical timing, existing melisma segments
and manually authored pages remain unchanged. A selection inside a melisma
starts at its word anchor; a selection inside a text fragment includes the whole
fragment. The lyric context menu also offers **Assign from this text position**.
Without a text selection, the button retains its original start-of-text behavior.

**Tools > Charts > Incomplete notes** lists missing lyric text and unassigned
pitches with their chronological note numbers and start times. Double-click
an entry or choose **Go to note** to reveal it in the chart and focus the missing
field. Chart/DLC exports open this list before asking for a destination; song
packs identify the affected song too. Missing-text notes have a red outline.
Draft projects can still be saved. MIDI export checks pitches, not lyric text;
LRC export checks text, not pitches.

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

In 0.4.6 Beta 2, selecting a row seeks to that word. The adjacent play-from-
selection button starts playback there. Editing a start seeks to the corrected
time, keeps its existing end and adjusts the previous interval if it was
connected. Manually shortened intervals retain their gaps. Undo/redo also seek
to the affected timestamp, including while recording remains armed.

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
