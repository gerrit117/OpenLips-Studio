# OpenLips Studio 0.1.0 Beta

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
- Select a note to edit start, length, MIDI pitch, text, word/phrase endings.
  Each visible monophonic note also has an inline lyric field below the grid.
  Exact next-page times can be specified on phrase-ending notes; otherwise
  imported UltraStar timing or the default preroll is used. See
  [pages and project semantics](studio_pages_and_community.md).
  Drag a note to change time/pitch; drag its right edge to resize. Double-click
  empty grid to create a note, or a note to edit its text in the inspector.
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
  it never changes chart/export timing. Negative offsets delay reference playback.
  Reference media is linked, not copied into the project. Without
  reference audio, playback is a visual cursor preview, not a synthesized song.
- Save `.olp` projects (versioned UTF-8 JSON, not a song package); atomic writes preserve the previous saved project
  when preparation fails. Relative audio/video links are resolved on reopening.
  Unfinished notes without lyrics can be saved, even when export would reject them.
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

The editor accepts MIDI pitches 0..127. OG export deliberately enforces the
existing writer's validated vocal/time/length constraints and rejects notes
without lyric fragments rather than silently changing them.

DLC export packages prepared xWMA/cover/video assets using a separately built
STFS executable. Structural/hash validation is not in-game discovery proof:
the existing custom DLC discovery issue is still unresolved. No FTP connection
or game installation is performed automatically. The native STFS/media
backends currently need separate Windows builds; editing/importing are portable.

## Modules and plugins

`studio/model.py` is independent of Qt; `importers.py` handles external formats;
`timeline.py` paints/interacts with notes; `app.py` owns UI state and transport;
`exporters.py` adapts validated tools. `lyrics_search.py` and `dlc_dialog.py`
use worker threads for network/package operations.

Importer plugins publish the `openlips_studio.importers` entry-point group.
Each factory returns `studio.plugins.ImportPlugin` with API version 1, a label,
extensions and an `import_file(Path) -> StudioProject` callable. Merely opening
Studio does not load plugins. The user must explicitly select a trusted plugin
in Tools. Plugins execute arbitrary Python; this is an opt-in contract, not a
sandbox or a plugin marketplace.

## Public-release checklist

This is the first beta foundation, not the end of repository cleanup. Existing
research tools/docs retain their paths. No private samples, generated songs,
media or copyrighted UltraStar examples are included in new Studio commits.
Previously tracked private assets may remain in Git history: audit licensing
and agree on history cleanup before declaring the whole repository safe for
public redistribution. Do not force-push a rewritten history without approval.

Before a public binary release: audit complete bundled third-party license
notices, verify macOS builds, review plugin packaging and install paths, finish
DLC discovery, and test longer real projects and audio synchronization.

References: [Qt deployment](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html),
[Mido timing](https://mido.readthedocs.io/en/latest/files/),
[LRCLIB API](https://lrclib.net/docs).
