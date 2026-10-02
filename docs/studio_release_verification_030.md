# Studio 0.3.0 Beta: release verification

Verified on 2026-10-02. This is a downloadable GitHub prerelease, not just a tag:
[0.3.0 Beta downloads](https://github.com/gerrit117/OpenLips-Studio/releases/tag/v0.3.0-beta.1).
The repository remains private; publishing the release did not make it public.

## Source and native builds

[Workflow run 36967997393](https://github.com/gerrit117/OpenLips-Studio/actions/runs/36967997393)
completed successfully, including the release job. Source commit:
`4c23ced4dfcd7e36d98190f3aeeae19344da4e61`.

| Native target | Selected regression suite | Frozen model / GUI / plugin checks | Distribution |
|---|---|---|---|
| Windows x64 | 79 passed, 2 Unix-only skips | Passed | ZIP and per-user installer EXE |
| macOS Apple Silicon | 81 passed | Passed, including actual .app plugin test | ZIP and DMG |
| macOS Intel | 81 passed | Passed, including actual .app plugin test | ZIP and DMG |
| Linux x64 / Ubuntu 22.04 | 81 passed | Passed, including desktop entry/icon installation | tar.gz |

Each target built and tested its independent Basic Pitch plugin and optional
AI engine. Frozen AI smoke tests recovered MIDI 57/62 from generated audio,
without external Python or model downloads. Native builds do not substitute for
heavy-model song inference on every operating system or every GPU.

The release contains **15 downloadable packages plus 15 SHA-256 files**:
four Studio archives, four Basic Pitch `.opl` packages, four independent AI
archives, one Windows wizard and two macOS DMGs. No songs, game binaries or
copyrighted test media are bundled. Larger AI model downloads remain optional.
All fifteen published checksum files were downloaded and matched against
GitHub's SHA-256 digests for their corresponding binary assets. This verifies
the published pairing; it is not code signing or a gameplay acceptance test.

The first native build failed two mocked Windows-media tests on Unix: changing
`sys.platform` also affected the real standard-library executable search. Tests
now stub that dependency explicitly; no platform failure was bypassed by
removing the tests or treating them as passing. The fresh native run passed.

All development changes were merged into `main` at `3836b70`. The application,
packaging recipes and workflow are identical to the successfully released source;
the later additions are native research tooling/documentation. The merge skipped
a duplicate rebuild of unchanged released code. Future work uses `main` only;
changed application code requires a new version and its own native release checks.

## Local checks and prepared tests

The complete local suite passed: **328 tests, 6 explicit skips, 11 subtests**.
Windows frozen Studio, standalone AI inference, actual Amazing separation/ASR
and experimental known-lyric alignment were tested. The local installer was
compiled successfully, but install/uninstall was not performed on this account.

The Desktop `OpenLips Tests` folder has reversible original/AI Amazing launchers,
restore, untouched OG/NoH ISO starts and an editable project opener. The newly
serialized AI pair has 220 MelodyMarkers/220 LyricMarkers and no graph errors.
The baseline/AI/restore file-switch cycle passed without launching Xenia.
Working Amazing chart/lyric hashes match the re-extracted backup after restoration.

See [AI song test report](ai_song_creation_test_report.md) for measured recognition
errors and the test order, and [song variants](ls2_song_variants.md) for the corpus
and exact-executable native short-mode findings.

## Still requires user or hardware verification

- Newly generated AI-pair loading, complete playback, page changes and scoring.
- Review of recognized sung words and experimental word alignment; these are
  not verified automatic syllable timings.
- Windows wizard install/uninstall and `.olp` Open With integration.
- macOS drag/install and Gatekeeper behavior; signing/notarization is pending.
- Linux desktop/audio behavior on distributions outside the CI baseline.
- Hardware acceleration: CPU is tested; driver/provider-specific GPU paths are not.
- NoH loading, complete QTE/duet/short-mode exports and new catalog previews.
- The separate 600-DLC baseline and optional personal edition.
