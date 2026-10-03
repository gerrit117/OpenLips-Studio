# Changelog

## Unreleased
### Changed
- Add an undoable Intelligent Page Breaks toolbar action that balances whole
  lyric passages using vocal pauses, punctuation, existing breaks and soft
  original-song layout targets; leave imported UltraStar pages unchanged.
- Base optional lyric-page defaults on original-song measurements: 30 characters,
  8 notes and 3 seconds, reducing crowded pages without altering note timing.
- Import multiple local UltraStar TXT files or recursive song folders with
  associated audio, video and covers; save projects or export a Song Pack
  directly from the start screen.
- Choose the destination folder when saving batch-imported projects.
- Accept terminal UltraStar line breaks without blocking DLC export or creating
  an empty next lyric page, including previously saved projects.
- Keep optional AI runtimes out of Studio installers and portable archives;
  download the matching runtime on demand, with CPU fallback when no AMD
  release is available yet.
- Integrate plugin commands into Studio's Tools menu, separate from plugin installation.
- Replace the external USDB Syncer window with native search and download controls.
- Add a built-in manual YouTube downloader and automatic UltraStar video-reference prompts, with bundled yt-dlp, Deno and FFmpeg.
- Download multiple USDB songs with covers and open direct Song Pack export.
- Preserve the full MIDI pitch range during export instead of rejecting notes above 84.
- Detect missing video soundtracks during song creation and offer audio selection;
  combine silent videos with separate audio automatically during DLC export.


- Add automatic GPU selection and AMD ROCm acceleration for vocal separation
  and PyTorch Whisper transcription, with explicit per-stage device reporting
  and CPU fallback. Keep pitch analysis on CPU.

- Split long lyric pages at word boundaries with adjustable readability limits,
  preserving notes, melismas and existing page breaks; retain word endings on
  continuation notes.

- Start 15-second menu previews at the first lyric entry instead of the media
  intro; generate and link a separate small video preview for video songs.
- Customize preview start and duration, saved with the project and shared by
  audio/video previews; offer MIDI-only file selection in MIDI setup modes.
- Assign LRC lyrics to existing MIDI notes as an editable timing-based draft,
  without changing pitches or durations; restore lyric-anchor review.
- Support larger DLC packs with verified level-2 STFS hash trees and bounded
  memory use during validation, replacing the initial 110 MiB limit.

- Export named multi-song DLC packs from the current chart and saved projects,
  with independent media, previews, covers and song entries.
- Copy verified exported DLCs to Xbox Content USB storage from Tools or directly
  after export, with progress, read-back checking and no overwriting.
- Preserve melisma notes without repeating their lyric fragments; correct
  Studio MIDI-to-Lips pitch conversion.

## 0.3.3 Beta

- Choose a destination folder for DLC export; generate an extensionless package
  filename from its finalized STFS header content ID, following the observed
  Lips marketplace naming convention. Existing packages are never overwritten.

## 0.3.2 Beta

- Adjust or mute reference audio independently of chart note tones.
- Move a selected note up or down one semitone with the arrow keys, with reference
  tones and undo/redo.
- Select multiple notes with Ctrl+click and merge consecutive notes of the same
  pitch from their context menu, combining timing and lyric fragments.
- Detect silent video sources and use an unambiguous companion audio file for
  analysis instead of failing with a raw encoder command error.

## 0.3.1 Beta

- Audition selected pitches with reference tones and optionally hear chart notes
  during playback, with a dedicated volume control.
- Download and verify missing native AI components automatically on first use,
  with progress and cancellation instead of a runtime-path setup prompt.
- Add a step-by-step song creation wizard and a dedicated export button.
- Prepare DLC media automatically on Windows: video conversion, full xWMA audio,
  15-second xWMA preview, cover generation and integrated STFS packaging.
- Generate package identities internally and validate audio decoding and package
  contents before publishing the output.
- Start with an empty project; opening or closing untouched new projects no longer
  asks to save them.
- Group Community upload (.ols) and DLC exports under File > Export. Community
  packages contain generated charts, lyrics, cover and metadata, without media.
- Hide analysis, note and MIDI controls while installing or selecting plugins.
- Add visible hover states to menus and toolbar buttons.
- Allow Windows installation for the current user or all users.


## 0.3.0 Beta

- Create editable chart drafts from audio with optional vocal separation,
  pitch detection and lyric recognition. Review, cancel or accept with undo.
- Import synchronized LRC lyrics and retain their timing in projects; optionally
  align supplied English/German words or use one note per word.
- Include offline pitch detection and offer a separate AI engine with selectable
  transcription models. Automatic singing recognition still requires review.
- Preserve synchronized lyrics from LRCLIB search results.
- Add a Windows installer and macOS drag-to-Applications DMGs.
- Clarify media requirements in English/German and fix the DLC dialog translation
  error. Final media conversion on macOS/Linux still needs compatible source files.

## 0.2.1 Beta

- Independent API-2 process plugins with platform-specific executable entrypoints,
  private runtimes/models and declarative UI parameters, without host Python imports.
- Basic Pitch moved entirely into `plugins/basic_pitch`; Studio no longer bundles
  its code, model or runtime. Four standalone platform `.opl` packages are released
  separately from the Studio downloads.
- Atomic background installation of larger native plugin packages, preserving
  executable permissions and validated internal symlinks; compatibility/path/size
  validation and rollback leave existing files untouched.
- Versioned request/progress/result protocol includes the current project snapshot
  for processing and future lyric-alignment plugins. Text settings are supported.
- Plugin catalog, complete developer guide, and independent lyric-mapping example.
- Legacy API-1 importers remain supported. Explicit activation and undoable draft
  acceptance remain required; process isolation is not a security sandbox.
- Native CI tests install the actual `.opl` into a separate directory and exercise
  real inference, previews and undo/redo through the frozen host app.

## 0.2.0 Beta

- Usable opt-in plugin manager with per-plugin settings, trusted local plugin folders
  and backward-compatible installed importer entry points.
- Portable `.opl` plugin packages with bounded, traversal-safe installation and
  explicit trust/activation; `.olp` remains the song-project extension.
- First built-in plugin: Spotify Basic Pitch, running locally in an isolated,
  bundled ONNX worker without a Spotify account, API key or audio upload.
- Adjustable detection thresholds, minimum duration and MIDI pitch bounds;
  optional strongest-note filtering for overlapping predictions.
- Background analysis, cancellation, bounded logs, note preview, MIDI draft export
  and explicit undoable note replacement preserving project metadata and lyrics draft.
- Approved OpenLips Studio wordmark in the editor toolbar, Windows executable icon,
  macOS app-bundle icon and Linux window/desktop integration artwork.
- Separate runtime dependency inventories and preserved shipped license notices.
- Synthetic regression tests and real inference smoke tests in native release builds.
- English-only release notes generated from this changelog.

## 0.1.3 Beta

- Explicit standard system UI font; offscreen screenshots load host system fonts.
- Native platform archives published to GitHub Releases after successful CI.

## 0.1.2 Beta

- Windows OG VC-1/WMA Pro media preparation with the native encoder bundled.
- Video soundtrack extraction, audio-only output and optional FFmpeg cover video.
- 432p output below the 720p ceiling, bounded header normalization and validation.
- Project cover references, thumbnails and always-present normalized DLC JPEGs.
- Undoable chart/page time shifts that survive project saving and export.
- New synthetic media/cover tests; new playback paths still need gameplay checks.

## 0.1.1 Beta

- Install required Qt graphics/audio libraries on Linux build runners.
- Avoid duplicate native CI builds when tagging the same main-branch commit.
- Windows, Apple Silicon, Intel macOS and Linux builds passed tests/frozen startup.

## 0.1.0 Beta

- Native modular desktop editor with horizontal Lips-inspired note bars.
- MIDI track/channel import, tempo-map conversion and UltraStar import.
- Note/lyric editing, phrase/word boundaries, undo/redo and project persistence.
- Reference-audio/video playback behind the grid, preview offset, following cursor,
  zoom and horizontal scrolling.
- Work-in-progress `.olp` projects with external media links and Save As.
- Optional LRCLIB search and opt-in importer plugin contract.
- Inline lyric fields, explicit next-page timing and opt-in syllable suggestions.
- UltraStar numerical phrase times now retained alongside existing note timing.
- Existing fresh OG chart writer and experimental STFS builder GUI adapters.
- Windows, macOS Apple Silicon/Intel and Linux native-build workflow;
  non-Windows verification remains pending until CI completes.

Version policy: 0.1.x patches, 0.2 next milestone, 1.0 first stable major release.
Package version `0.1.0b1` represents display version `0.1.0 Beta`.
