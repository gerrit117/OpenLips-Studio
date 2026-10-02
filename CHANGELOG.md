# Changelog

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
