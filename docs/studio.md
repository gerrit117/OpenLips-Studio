# OpenLips Studio

## Start

Python 3.11 or newer:

```sh
python -m pip install -e ".[dev]"
python -m studio
```

Windows native build:

```sh
python -m PyInstaller --noconfirm OpenLipsStudio.spec
```

Run `dist/OpenLipsStudio/OpenLipsStudio.exe`. Keep the entire directory,
including `_internal`; this is not a single-file executable. macOS uses the
same sources, but must build on macOS. CI prepares separate target-native
artifacts for Apple Silicon/Intel and Linux x64. End users of these bundled
artifacts do not need Python installed. See [platform builds](studio_platforms.md).
macOS/Linux runtime acceptance has not yet been verified locally.

## Editor

Time runs left to right on a continuous horizontal timeline. During playback,
notes move left past the following cursor. Scrolling is horizontal; vertical
position represents pitch. MIDI note names use C4 = 60, not inferred song keys.

- Import a MIDI and choose one track/channel. Tempo changes become absolute
  seconds; the edit grid uses initial BPM. Type 2 and SMPTE timing are rejected.
  Sustain, overlapping notes and percussion generate warnings.
- Import UltraStar TXT through the existing parser, preserving source timing.
- Batch-import UltraStar files or song folders with their media and covers;
  choose the project output directory or export a Song Pack directly. Pages
  are optimized automatically without retiming notes. Explicit manual layouts
  stay intact; single-file import retains source pages.
- Start with LRC only to create editable grey blocks with unassigned pitches,
  or use the Timing Assistant to record word/syllable onsets with Space and
  review them with ticks. Ordinary LRC contains line starts rather than exact
  word lengths. See [lyric-first creation](lyric_first_workflow.md).
- Record page switches using the keyboard toolbar button: Space starts playback
  when paused and records a cut while playing; Esc ends recording. Presses in
  pauses retain their exact timing; presses inside words snap to a safe word
  boundary. Clear existing switches through Tools when starting a new layout.
  Both recording and clearing are undoable and never retime notes. See
  [chart quality and native scaling](chart_quality_investigation.md).
- Select a note to edit start, length, MIDI pitch, text, word/phrase endings.
  Each visible monophonic note also has an inline lyric field below the grid.
  Exact next-page times can be specified on phrase-ending notes; otherwise
  imported UltraStar timing or the default preroll is used. See
  [pages and project semantics](studio_pages_and_community.md).
  Drag a note to change time/pitch; drag its right edge to resize. Double-click
  empty grid to create a note, or a note to edit its text in the inspector.
  Up/Down changes selected pitches. Ctrl-click selects several notes for a
  compatible-pitch merge through the context menu. Right-click also provides
  splitting at the pointer or estimated word division. Pitch/text edits preserve
  the precision of untouched timing fields.
- Use the song-text panel to assign fragments from the selected note onward.
  Spaces separate words, newlines mark phrase endings. Optional `|` separators
  explicitly split syllables. An optional English/German dictionary-hyphenation
  suggestion modifies only the draft, not the notes. This is experimental:
  typographic hyphenation is not necessarily how a singer divides syllables.
  Review the draft and explicitly assign it; undo restores the note mapping.
  This explicit experimental assignment is undoable and never runs automatically
  on UltraStar import. Dense/polyphonic MIDI needs melody cleanup first; overlapping
  note starts may not have enough horizontal space for simultaneous lyric fields.
- Load local reference audio and/or video and play/pause/seek, change speed or zoom.
  Video appears behind the note grid and can be hidden independently. If both
  are supplied, video audio is muted and reference audio is the master clock.
  The preview offset uses `media_time = chart_time + reference_offset`, in seconds;
  it never changes native chart timing. MIDI/LRC interchange exports apply the
  offset to match the media clock. Negative offsets delay reference playback.
  Reference media is linked, not copied into the project. Optional note tones
  and note audition work independently of reference media, with separate volume
  controls. Unassigned lyric blocks do not play an invented pitch.
- Save `.olp` projects (versioned UTF-8 JSON, not a song package); atomic writes preserve the previous saved project
  when preparation fails. Relative audio/video links are resolved on reopening.
  Unfinished notes without lyrics or assigned pitches can be saved, even when
  export would reject them.
  The temporary `.olips` extension is also accepted when opening older projects.
- Undo/redo covers note and metadata edits, import replaces the project after
  confirmation. Freeform lyric draft typing uses the text widget's own undo.

LRCLIB search is opt-in and sends only title/artist after confirmation. It
requires internet but no API key. Results are drafts, not automatic syllable
alignment, and users remain responsible for lyric/media rights.

## Exports and limits

Debug JSON feeds the existing tools. Fresh OG X360 chart/lyric export delegates
to the runtime-tested `build_owned_chart` serializer, without using templates.
Choose a new output directory and the already-converted audio asset filename.
This export does not transcode media or register a disc song in MusicDB.

The editor accepts MIDI pitches 0..127, plus an explicit unassigned state for
lyric-first drafts. The current writer supports the full MIDI pitch range;
export validates timing, lyrics and assigned pitches rather than inventing them.
Enhanced LRC and MIDI exports are available for interchange.

Windows DLC export includes the STFS and media backends. It converts reference
video/audio, extracts xWMA audio, creates a default 15-second audio preview
from the first lyric (adjustable), cover and optional menu video, then packages
one song or a named Song Pack. Choose the destination; no backend paths need
to be entered. Song packs optimize pages on copies by default, retaining
explicit manual layouts. See [packs and USB transfer](song_packs_usb.md).

Custom DLC has been recognized and played in Number One Hits on a modified
Xbox 360 in user testing. Structural/hash validation alone is not game acceptance;
Xenia DLC discovery remains unresolved. No FTP connection or game modification
is performed automatically. macOS/Linux editing/import are portable, but game
export still requires [already-compatible media](studio_media.md).

## Modules and plugins

`studio/model.py` is independent of Qt; `importers.py` handles external formats;
`timeline.py` paints/interacts with notes; `app.py` owns UI state and transport;
`exporters.py` adapts validated tools. `lyrics_search.py` and `dlc_dialog.py`
use worker threads for network/package operations.

The plugin manager supports opt-in installed entry points and trusted local
plugin folders, parameters, background jobs, result previews and undoable
acceptance. API-2 plugins have independent native runtimes and communicate through
JSON rather than importing host Python. Basic Pitch is an optional separate `.opl`
package, not built into Studio. See the [plugin guide and API](studio_plugins.md)
for setup, limitations, development and credits. Plugins are trusted code, not
sandboxed. Merely opening Studio does not execute third-party plugins.

## Release and testing notes

This remains an early beta. README screenshots use original synthetic charts,
not licensed songs or game assets. Releases bundle third-party notices and
target-native runtimes. Windows builds receive local synthetic UI/export tests;
these do not replace console tests or verify macOS/Linux runtime behavior.
The Community tab is prepared, but the website is not publicly launched.
Report failures with the app version and reproduction steps; keep licensed
media, private credentials and original game files out of public reports.

References: [Qt deployment](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html),
[Mido timing](https://mido.readthedocs.io/en/latest/files/),
[LRCLIB API](https://lrclib.net/docs).
