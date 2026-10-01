# Next Studio development checkpoint

2026-10-01. Development snapshot, **not a new binary release**. The last
published release remains 0.2.1 Beta. No game or sample files were modified.

## Implemented and locally tested

- API-2 `song-import` result support and persistent adoption of declared
  UltraStar/audio/video/cover files. Acceptance replaces the current song,
  is undoable, and clears its old save path to avoid overwriting another `.olp`.
- USDB Syncer source bridge using upstream `MainWindowDidLoad` hooks and the
  original GUI/downloader. Source runtime is isolated/pinned. The upstream
  `#VIDEO` parser and owned-fixture export passed an offline test.
- Cooperative interactive cancellation via `cancel.request`; the bridge calls
  the upstream window cleanup, not a forced worker kill during a download.
- DE/EN UI catalog and Language/Sprache menu. Selection persists and changes
  the editor without changing notes, project content or undo history. Plugin
  parameters use translated labels; independent upstream UI/logs and technical
  errors may still use their own language.
- Media dialog no longer requires manual encoder paths. Windows uses the
  bundled native helper; FFmpeg is resolved automatically. The build spec adds
  the imageio-ffmpeg binary. macOS/Linux explain the current final-codec limit
  before attempting conversion.
- Local suite: **241 passed, 3 skipped, 11 subtests passed**. GUI source smoke
  screenshot inspected on Windows. No claim of new macOS/Linux native tests.

## Required before release

- Freeze/package USDB independently for Windows, macOS Intel/ARM and Linux.
  Include FFmpeg **and FFprobe**, Deno, upstream fonts/resources, license-hash,
  complete upstream license/source notices and exact dependency inventory.
- Test the actual upstream window, login and one authorized download/send flow.
  An offline export fixture is not an authenticated download test.
- Test cancellation while yt-dlp/FFmpeg jobs are active, on each platform.
- Add USDB native `.opl` artifacts and their checksums to CI and release gates.
  Do not reuse Basic Pitch's NumPy environment for Syncer dependencies.
- Preserve FFmpeg binary notices/source obligations before distributing the
  updated Studio archives. Verify automatic executable lookup in frozen apps.
- Run frozen GUI/worker acceptance smoke tests and the full native matrix;
  only then bump the app version and publish a release.

## Latest media request

User observed the Windows-backend message in the **macOS release** and asked
for alternatives on every platform. Findings and a concrete evaluation plan
are in [cross-platform backend research](cross_platform_media_backends.md).
MainConcept is a vendor-documented candidate; WMA Pro, Apple Silicon, licensing
and game compatibility are not yet confirmed. No codec substitution was enabled.

## Offline codec and catalog investigation

The user is away from the PC, so the pending Xenia input/profile handoff is not
actionable. No codec probe was installed into game files. Instead the expanded
[591-file census and native RIFF parser study](media_codec_corpus.md) establishes
WMA Standard in original xWMA full-song assets, distinct from ASF WMA Pro movie
audio. Portable audio-only xWMA is the next candidate; full seeking/playback
validation and portable new-video encoding remain unresolved. Do not replace
the accepted backend based on corpus or parser support alone.

[Large-library performance](large_song_library_performance.md) is separate,
optional game-side research. The source can rebuild the full active menu on
each install event; frequency/cost and a 600-song runtime must be measured
before implementing a coalescing patch. No game optimization was applied.

Local project suite after the new diagnostic tools: **257 passed, 3 skipped,
11 subtests passed** (`pytest tests`). Bare repository-wide pytest also finds
the ignored upstream USDB checkout, which requires its separate environment;
that upstream collection failure is not a Studio test failure.

## Portable media notices

The conversion and DLC dialogs now explain the pre-encoded media requirement
on macOS/Linux in both UI languages. READMEs and studio_media.md contain exact
tested OG settings and separately labelled DLC corpus profiles. Codec-patching
the game remains optional, unimplemented research, not a replacement for the
standalone builder or the working Windows backend. Existing downloads have not
been rebuilt for these notices yet. Full suite: 270 passed, three skipped,
eleven subtests passed. Platform-specific notices were exercised with simulated
macOS/Linux platform values on Windows, not native macOS/Linux encoding tests.
