# OG chart clock investigation

## Completed comparison: September 30, 2026

The current fresh chart's clock is NOT stalled. Both measured runs use the
same native Start/Update addresses, emulator build, full Original Video mode,
offline test profile, original Amazing media and isolated catalog slot.

| Chart | Start calls/completions | Post-Start samples | Host span | Chart advance |
|---|---|---|---|---|
| Original Amazing | 1 / 1 | 115 | 58.184915 s | 58.174700 s |
| Fresh four-note v6 | 1 / 1 | 170 | 86.185361 s | 86.173701 s |

In both runs, every captured post-Start update has started=1. The audio
object is null, the movie object transitions from state 1 to 2, movie_started
is 1, and the media base is 0.575034 seconds. Frame deltas are nonzero.
Original note/lyric changes were visible. Fresh `New Lips test song` progressed
from partial red highlighting to all four words red; afterward its completed
page remained on screen while the clock continued.

The four-note chart has a single lyric line and no subsequent Section page
break until 189.8 seconds. Page-based bars remain positioned on that page;
their fixed positions after the last note are not evidence of a frozen clock.
This explains the apparent stationary display in the current controlled test.
Historical variants and ABC's audio-only issue have not been re-measured;
do not generalize this conclusion to those files or all Lips generations.

### Control without probes

Generated a fresh six-note, three-line pair from
`examples/synthetic/chart_clock_pages.json`. Timings are 4.55/6.0,
14.55/16.0 and 24.55/26.0 seconds. Section page boundaries are 3.75, 13.75,
23.75 and 189.8 seconds. No source heap or root hash was copied.
Launched the same emulator with `lips_clock_trace_path` empty (verified in
config), so no HIR clock probes were emitted. The first page `First line`
was observed with an active partial highlight, and later the distinct third
page `Third line` with advancing/final highlights. This independently verifies
time-driven page replacement; the second page transition was not captured.

No clock patch or new chart ownership structure was needed. Builder
serialization remains unchanged in this iteration. Its stale frozen-clock
description and documentation were corrected. Remaining work includes final
page/outro presentation, real UltraStar many-page validation, audio-only mode,
media compatibility and independent catalog registration. These diagnostic
slot tests are not a complete standalone song pipeline or verified scoring.

### Probe correction and validation

The first instrumented original-control attempt crashed in host code before
writing a trace. Symbol lookup mapped host RVA 0xF29AB0 to a Function RTTI data
symbol, not a guest game function. The probe mistakenly used HIR `Call` for a
host builtin. Replacing it with `CallExtern` fixed that instrumentation bug;
the corrected build completed and both controls ran. The committed patch
contains the corrected call. Do not count this host crash as a game/chart
failure or evidence against renamed intro files.

All 138 tests and 11 subtests pass, including synthetic trace classification
and six-note page-boundary validation. Xenia is closed. Original Amazing chart
and lyric were restored from the re-extracted backup and SHA-256-verified.
The three `.wmv.bak` intro renames remain, matching the user's preference;
all three completed tests booted without a visible missing-intro error.
Trace files, generated IXBs, game assets and decompilation stay private.

Confidence is high for these controlled OG runtime results. Scope is one
original Amazing pair and two synthetic pairs, not an all-corpus invariant.
Corpus-wide serialization findings remain in the existing separate reports.

The checkpoint below records the earlier pause and is retained as history;
its pending tests have now been completed as described above.

## Checkpoint: September 30, 2026

Paused at the user's request before launching either comparison run. No
cause of the stationary fresh chart has been demonstrated yet. Native
analysis identifies useful measurement points, not a verified builder fix.

The exact executable used for this analysis is OG Lips 2008, title 4D530888,
version 0.0.0.20, SHA-256
`95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9`.
Addresses below must not be applied to Number One Hits or another executable.

## Native anchors

Read-only Ghidra analysis traced Lua registration and wrapper calls:

| Operation | Address | Evidence |
|---|---|---|
| Start Lua wrapper | 0x82CC5C80 | Registered as Start; unwraps ChartPlayer |
| Native Start | 0x82D62AD0 | Wrapper call; r3=this, f1=start time |
| Start observation after flag store | 0x82D62FC8 | Previous instruction sets this+0x168 |
| Native Update | 0x82D64C90 | Updates elapsed clock and media/sequence state |
| LoadMusicFromSequence | 0x82D64190 | Lua wrapper call; r4=this, r3=result storage |
| LoadMovieFromSequence | 0x82D63F10 | Lua wrapper call; r4=this, r3=result storage |

`tools/ghidra/StudyOgChartClock.java` finds registration strings, references,
candidate instruction references and clock-field writes. Candidate string
references need assembly verification. Run with `-readOnly -noanalysis`;
temporary disassembly changes must not be saved. Existing
`StudyOgIxbReader.java` was used for bounded function decompilation.
The FPR-save helper still confuses the Update decompiler's argument recovery;
do not infer the native calling convention from that pseudocode alone.

Observed runtime fields, specific to this executable:

| Offset | Interpretation |
|---|---|
| 0x168 | Started flag |
| 0x16C | Media-start gating state; full meaning unresolved |
| 0x164 | Runtime music index |
| 0x18C / 0x190 | Conductor agent / tempo conversion object |
| 0x22C / 0x230 | Audio / movie playback objects |
| 0x264 / 0x268 | Audio / movie started flags |
| 0x26C / 0x270 / 0x274 | Music delay / media base / movie delay |
| 0x278 / 0x27C | Current / previous chart time |
| 0x25C | Subtracted by GetElapsedTime |
| 0x334 | Frame delta when started |

Update chooses audio position when an audio object is in state 2. If there
is no audio object, it can instead choose movie position in state 2.
Otherwise it can add the frame delta subject to its threshold check.
Thus both a missing start and a nonadvancing media position are candidates;
neither is confirmed. Video advancement alone does not prove chart-time
advancement. Static note positions alone also do not prove a frozen clock.

## Probe implementation

`tools/xenia/og_chart_clock_trace.patch` is an optional research patch against
the local Canary source at aee0871. It adds read-only HIR builtin callbacks
at the three Start/Update addresses. Context barriers publish registers;
callbacks do not call guest methods, modify registers or write guest memory.
Mapped/readable guest ranges are checked before field reads. Update samples
are bounded to 180 per object, at most twice per second. Output is private
key/value text; no lyrics or memory dumps are included.

Enable only for the exact verified executable above:

```text
--lips_clock_trace_path=<private trace path>
```

The path must exist as a parent directory. Use a distinct filename per
emulator process. The patch has fixed addresses, not automatic title detection.
It is disabled when the option is empty. Native measurements have NOT yet
been collected, so probe runtime correctness is not yet verified.

The external Xenia build completed successfully. The instrumented executable
is at `xenia-research/xenia-canary/build/bin/Windows/Release/xenia_canary.exe`.
It has NOT yet replaced the isolated emulator executable. Existing external
keyboard/kernel changes were left intact. The three CPU edits remain in the
external source, and their reproducible diff is saved in this repository.

Summarize two captures with:

```text
python tools/analyze_chart_clock_trace.py original.trace fresh.trace
```

The summarizer separates post-Start observations, reports clock advancement,
and labels captures shorter than five seconds insufficient. It does not
establish a media or serialization cause automatically.

## Resume procedure

1. Verify original Amazing chart/lyric hashes in the isolated game copy.
2. Copy the instrumented emulator there, retaining the working offline profile
   and keyboard configuration. Launch with an original-specific trace path.
3. Inspect boot using Computer Use. If missing intro files trigger an error,
   stop the run and ask the user to restore their names, as requested.
4. Navigate to full Original Video Amazing; observe at least 20 seconds of
   gameplay. Verify probe Start and Update fields are plausible.
5. Close Xenia, substitute only the existing fresh v6 chart and accepted v5
   lyric in the isolated Amazing slot, then repeat identical navigation and
   capture with another filename.
6. Compare started flags, frame deltas, current clock, media states and timing
   bases. Only then choose a narrow additional native probe or builder fix.
7. Restore original chart/lyric and verify hashes after testing.

No game was launched, no chart/lyric substitution occurred at this checkpoint.
Original Amazing in the isolated copy remains verified:

| File | SHA-256 |
|---|---|
| Amazing.X360 | 0CB0F29D229579E749090B9DF015F87E254DEDA627210C0CFA2D20FB240272D8 |
| Amazing_Lyric.X360 | 8BC338A2F96C88E4A145E71913E569433464DDC21E54F4F43ABB445E5252FABB |

The three isolated intro files MGS_Logo.wmv, iNiS_Logo.wmv and LipsOP.wmv were
renamed to `.wmv.bak`, mirroring the user's changes to their extractions.
They have not yet been boot-tested. No original extraction, sample asset,
private trace or generated pseudocode is included in this commit.
