# Studio 0.4.0 Beta verification

Local verification on Windows, 2026-10-06. Test content is synthetic and
original; no commercial songs or game assets accompany this report.

## Automated coverage

- Full suite: **644 passed, 16 skipped, 11 subtests passed**.
- LRC-only wizard, ordinary/enhanced LRC drafts, missing-pitch validation and
  project round trips.
- Word/explicit-syllable tokenization, tap recording, final-end recording,
  blank taps followed by lyric assignment, undo/redo and normal Space text entry.
- Tick scheduling, seeking, playback-rate changes and tick disabling.
- Note splitting, melisma continuations, pending-pitch merging without fake
  audition, pitch assignment and unchanged fractional timing on pitch edits.
- Enhanced LRC/MIDI media-clock exports and refusal to overwrite files.
- Automatic page preparation and Song Pack chart generation on owned copies,
  preserving note data and explicitly marked manual page switches.
- Manual page-switch recording and its existing safety/undo tests.

Skipped tests include platform/optional-runtime tests; this result is not a
claim that every platform or GPU backend was exercised.

## Interface and package checks

README images are captures from the actual Qt application with original demo
lyrics. Editor, LRC draft, creation wizard, timing assistant and prepared
Community sign-in views were inspected. A compact editor viewport was checked
as well. The cross-platform wizard style keeps navigation inside its window.

The Windows frozen app is checked separately from source execution. A synthetic
audio/video export exercises the bundled encoders and STFS backend, validates
the package hashes and linked XML, and checks full audio, 15-second preview
audio and the small menu video. This is structural/export validation, not an
Xbox or Xenia acceptance test.

A native two-song synthetic Song Pack also passed encoding, STFS hashing,
XML packaging and chart extraction checks. The automatically prepared chart
contained its new page switches; the second chart retained its explicit
1.3-second manual switch. Both source project objects remained unchanged.

## Please Check On Your Setup

1. Batch-import a small real collection, save it to a chosen directory and
   export a Song Pack. Compare crowded passages on the Xbox with your earlier
   exports; note timing and pitches should remain unchanged.
2. Record a manual page layout, save/reopen it and include it in an automatically
   optimized Song Pack. Its deliberate switches should be retained.
3. Try LRC only with your reference song. Assign pitches, split a sustained word
   across notes and verify the melody with note tones.
4. Record words or `|`-divided syllables in the Timing Assistant. Listen to ticks
   with reference audio, seek, slow playback and re-record a passage. Check
   audible synchronization and your audio-device behavior.
5. Save an unfinished grey-block project, reopen it and finish it. Export LRC/MIDI
   and verify their alignment with the same reference media.
6. Install/update using the Windows installer with your preferred per-user or
   all-users scope. Your projects and plugin settings should stay intact.

macOS/Linux runtime and installation checks remain target-machine work. Their
media conversion restriction is unchanged. The Community website remains
**coming soon**, so these tests do not depend on public registration.
