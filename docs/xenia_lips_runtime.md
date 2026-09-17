# Lips Runtime Research in Xenia

## Scope

This note compares current Xenia and Xenia Canary behavior relevant to Lips. It
also defines the next reproducible runtime tests for OpenLips. No game binaries,
logs, or copyrighted assets are stored in this repository.

Research snapshot: 2026-09-17.

## Repositories and Issues

- Standard Xenia: <https://github.com/xenia-project/xenia>
- Xenia Canary: <https://github.com/xenia-canary/xenia-canary>
- Original Lips compatibility issue: <https://github.com/xenia-project/game-compatibility/issues/1618>
- Current Canary Lips issue: <https://github.com/xenia-canary/game-compatibility/issues/1119>
- USB microphone request: <https://github.com/xenia-canary/xenia-canary/issues/1051>
- Canary XMP fix: <https://github.com/xenia-canary/xenia-canary/pull/1042>

## Main Finding

"No microphone support" is not a sufficient explanation for the original Lips
startup crash.

Historical original-Lips logs show this order:

1. The title sends XMP messages `0x00070044` and `0x0007002B`.
2. Old Xenia returns an unimplemented/failure result.
3. Lips creates four `AudioCapture` threads.
4. The title repeatedly calls `XamUserGetDeviceContext` for device class `4`.
5. The old build eventually crashes in guest code.

Canary PR #1042 changed the XMP media-source, dashboard initialization, and
workspace paths to return usable success results. Maintainers and users then
reported that original Lips reaches and remains stable in the menu and songs,
without microphone scoring. This makes XMP startup behavior the demonstrated
old startup blocker and microphone capture a separate missing feature.

Later Lips releases may still hang during profile, storage, DLC catalog, or
database initialization. Reports for Party Classics, Number One Hits, and I
Love the 80s must not be generalized from original Lips behavior.

## Standard Versus Canary

The inspected standard Xenia source does not implement the XMP message handling
that fixed original Lips. Its `XamUserGetDeviceContext` implementation also has
no microphone-specific device result.

Current Canary contains:

- XMP handling from PR #1042.
- `XamUserGetDeviceContext` recognition of microphone device class `4`.
- an experimental `allow_mic_initialization` setting.
- a first `MicDeviceRequest` stub for status, start, gain, data, sample-rate,
  and capability request IDs.

The current microphone implementation is not an audio backend. With
`allow_mic_initialization=true`, status reports a connected device, but
asynchronous start/data requests currently complete with an unsuccessful
status. No host PCM capture is copied into guest buffers.

## Relationship to OpenLips Findings

The pulled OpenLips work at `bf67238` strengthens the template-preserving path:

- 111/111 supported plain chart files and 111/111 supported plain lyric files
  survived byte-identical section split/rejoin tests.
- Same-size lyric payload edits and capacity-preserving full visible lyric
  replacement have loaded on real hardware.
- A valid edit may appear ineffective when a duplicate/version-specific
  deployed resource is loaded instead.
- Synthetic IXB failures remain consistent with missing runtime ownership and
  object-graph semantics, not with basic marker timing or lyric encoding.

These findings agree with the earlier crash work, but change the practical
priority. We can continue useful template-preserving chart work now. A working
Canary runtime will make it much faster to discover which file instance and
object graph the title actually loads before returning to fully synthetic IXB
construction.

## Recommended First Runtime Matrix

Use the latest `canary_experimental` release, not standard Xenia. Keep the
emulator and test content in an isolated portable directory.

Common diagnostic settings in `xenia-canary.config.toml`:

```toml
[General]
debug = true

[Kernel]
allow_mic_initialization = false

[Logging]
flush_log = true
log_level = 3
log_mask = 0
```

Run these controlled cases in order:

| Case | Title/content | Mic initialization | Purpose |
| --- | --- | --- | --- |
| A | Original Lips, no TU/DLC | false | Confirm XMP-fixed baseline reaches menu/song |
| B | Original Lips, same files | true | Observe current MicDeviceRequest request sequence |
| C | Known-working real song | false | Establish file-load and playback baseline |
| D | Template-preserving OpenLips edit | false | Verify exact deployed chart/lyric path |
| E | Synthetic test song | false | Capture first semantic load divergence |

For later-generation titles, test `mount_memory_unit=true` separately because
they may require the storage selector and database initialization path. Do not
combine this variable with microphone changes in the same run.

Analyze each produced log with:

```powershell
python tools/analyze_xenia_log.py C:\path\to\xenia.log
```

## Next Emulator Work

The smallest useful emulator change is not full USB passthrough. It is an
instrumented null-capture implementation:

1. Log every `MicDeviceRequest` request type and the request-specific union
   fields before writing them.
2. Confirm callback arguments and event behavior from a real Lips run.
3. Implement one connected mono PCM device that returns correctly sized silence
   and completes asynchronously with success.
4. Only after song playback is stable, connect a host capture API and copy real
   PCM samples into the verified guest buffer layout.

This ordering avoids guessing the undocumented request union. The existing
Canary stub already shows that returning `PENDING` and then an unsuccessful
callback is intentional scaffolding, not a finished device.

## Open Questions for the Next Run

- Exact Lips edition, media ID, title update, and Canary commit being tested.
- Whether failure occurs before title screen, on Start, during database loading,
  on song selection, or when gameplay begins.
- Which XMP messages and `MicDeviceRequest` actions occur immediately before the
  failure.
- Whether the title reads the expected template-edited chart and lyric paths.
- For later games, whether the wait is in storage UI completion, content
  enumeration, DLC reconciliation, or SQLite/database startup.
