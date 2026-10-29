# Studio Workflow (Beta 16)

The redesign keeps Qt Widgets and the existing import/export, library and
analysis services. The generated references are in `design/studio-workflow-v1`;
the README editor screenshot is captured from the real application with
synthetic media, not from those references.

## Authoring

1. **Source:** choose local media or download from a YouTube URL with permission.
   Existing projects, UltraStar, MIDI and batch/USDB imports remain available.
2. **Tempo & Key:** review local BPM/key proposals, correct them manually, set a
   beat offset and listen with a metronome. A video without audio uses the existing
   soundtrack selection check. Preparation can happen before any project save.
3. **Lyrics:** load LRC/plain text, search, transcribe or record word timing.
   A beat-based draft is explicit and unpitched; it is not vocal transcription.
4. **Melody:** edit notes alongside flowing lyrics. Select a note and click a word,
   or drag a word onto a note. Consecutive selected notes can share one word as a
   melisma. Expert view restores numerical note/syllable controls.
5. **Review & Export:** open the existing correction/page-layout tools and export
   community songs, DLCs or song packs. Save updates the current project.

The header distinguishes an unsaved session, unsaved changes and a saved project.
There is no new automatic project-saving promise. Downloads are retained outside
the temporary worker directory so project links survive download cleanup.

## Analysis Limits

- Analysis decodes at most the first 120 seconds locally and shows that segment's
  waveform. Existing full-song playback remains unchanged.
- BPM uses the existing beat detector. Major/minor key proposals compare librosa
  chroma with Krumhansl/Kessler profiles. There is no claim of guaranteed accuracy,
  vocal separation, tempo-map detection or recognition of every musical mode.
- Changing BPM/key in preparation never rescales existing note seconds or pitches.
- The optional AI workflow and its separately downloaded runtimes remain separate.

## Verification

`tests/test_studio_workflow.py` covers navigation, shared lyrics, occurrence-aware
assignment, melismas, drag payload validation, key-profile rotation and cancelled
media adoption. `tests/test_source_download.py` tests handoff without network
access or a real user library. `tests/smoke_workflow_ui.py` renders each actual Qt
step using generated audio/lyrics and isolated preferences, including small
window sizes. Network provider availability and Xbox playback are separate tests.

Analysis references: [librosa chroma extraction](https://librosa.org/doc/main/generated/librosa.feature.chroma_stft.html)
and Krumhansl & Kessler (1982), *Tracing the dynamic changes in perceived tonal
organization in a spatial representation of musical keys*.
