# Changelog

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
