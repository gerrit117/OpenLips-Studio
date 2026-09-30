# OG chart clock investigation

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
