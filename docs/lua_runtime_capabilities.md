# OG Lips Lua runtime: capabilities and limits

Status: 2026-09-30. This is analysis of the user's local, original OG 2008
game files; no game script or XEX is committed or distributed here. The
optional Lua/debug path does not replace the standalone IXB song builder.

## What runs in retail?

The disc contains readable `lps/Script/*.lua` sources and a 582,404-byte
compressed `lps/Assets/PackedScript.X360` (magic `0FF512ED`). A previous
isolated experiment added a post-initialization `bVersionText` override to
loose `Main.lua`; no version text appeared in game. See
`debug_lua_test1_summary.md`.

On September 30, an isolated Xenia build logged guest `NtCreateFile` paths
from boot through the title screen. Among 532 file-open attempts it observed
`game:\lps\Assets\PackedScript.X360` and **zero** loose `.lua` paths. This
confirms the packed file is opened in this retail startup path and explains
why the loose-source edit had no visible effect. It does not prove that every
later state or game variant never reads a loose script. The temporary Xenia
trace was removed and the emulator rebuilt afterward. Do not assume editing
a loose `.lua` enables a retail debug feature.

`Settings.lua` initializes `bEnableInGameDebugCommands = true` in source,
then explicitly sets it to false when `LPS_LUA_RELEASE == 1`. The release
condition must be measured in the running game; the test above did not
verify its runtime value. A safe path is to trace the packed script load and
test one reversible log/display hook in the isolated Xenia copy before
enabling any controller debug commands.

Setting `LPS_LUA_RELEASE` to zero has **not** been tested. The conditional in
`Settings.lua` only controls debug defaults after the script is running. It
does not select a source file or prove that loose Lua will be loaded. A
read-only Ghidra audit of the verified OG XEX found `PackedScript/` and
`require( "Script/Main" )` in the executable's script-related string area,
along with the `LPS_LUA_RELEASE` name. Automatic xrefs are incomplete there,
so their precise native call order remains unresolved. The startup file-open
trace is stronger evidence: the packed resource was opened, and no loose
`.lua` was opened in the observed boot.

`PackedScript.X360` likely supplies executable script content, but its internal
representation and coverage have not been decoded or proven. A debug flag
cannot be assumed to swap that content automatically. Editing loose source,
editing the packed resource, or hooking the native Lua loader are distinct
experiments; only the first was tried, with no visible effect.

The audit is reproducible with `tools/ghidra/StudyOgLuaLoad.java` against the
OG project, read-only. Its private output is not included in this repo.

## Useful existing hooks for custom-song tests

| Area | Script evidence | Use and limit |
| --- | --- | --- |
| Load phases | `Main.lua`: `LoadInGamePackages`, `ChartDisplayPrepare`, `InitializeGameSoundData`, `CreateChart` | Identify the first failing stage. Native functions do the actual package and chart work. |
| Playback | `LpsUtilities.lua`: `_GetChart`, `_LoadChart`, `_LoadMusic`, `_LoadMovie`, `PlayChart`, `_ChartPlayer:Start(0.0)` | Compare media-load success with chart-start success. |
| Clock | `Main.lua`: `ClearMusicTimeTempoMap` and `SetMusicTimeTempoMap` around TitleCall; `LpsUtilities.lua`: `IsChartStarted`, `GetChartLength` | Strong diagnostic candidate for the generated chart whose notes display but do not advance. |
| Marker view | `ChartRenderer.lua`: `SpawnPhraseMarker`, `SpawnHitMarker`, `SpawnScreamMarker`, `SpawnPitchLine` | Shows marker timing and pitch become screen coordinates through native renderer methods. Does not define IXB serialization. |
| Lyric view | `Chart/LyricRenderer.lua`: page creation and `AppSetting.showMarkerLyrics` | Helpful to distinguish incorrect mapping/text from wrong timing. |
| Chart debug overlay | `LpsUtilities.lua`: `OutputChartPlayerState`; `Main.lua` calls it during play | Shows tone, input, pitch distance, combos, mic stats and page/marker counts if release gate is open. It performs divisions by chart durations/page counts, so test on a known-good chart before tiny synthetic charts. |
| Debug menu | `Main.lua`: `lpsDebugMenu`, gated by `bEnableInGameDebugCommands` | Includes `Master Offset`, `Show pitch line`, lyrics under markers, LEDs and mic controls. `SELECT + RUP` toggles it in source; routing in retail is unverified. |
| Test/preview | `LpsUtilities.lua`: `EnableTests`; `ChartPreview.lua` preview lifecycle | Developer tools/API examples, not proof of a retail hot-reload or standalone-song importer. |

The first bounded instrumentation experiment, after confirming the active
script source, should log only song ID, load-stage completion, `IsStarted`,
chart elapsed time, chart length and media load results on a known-good
song and on the generated four-note chart. Avoid enabling the entire debug
overlay until its zero-count assumptions are understood.

## What the scripts can influence

Subject to the retail loading gate, Lua controls substantial orchestration:

- Menu state transitions, song selection and play options (`Main.lua`,
  `Menu/*.lua`). UI assets/animations are separate resources.
- Chart and lyric rendering callbacks, page visuals and pitch/marker display
  (`Chart/*.lua`). Native code owns IXB deserialization and core sequence
  playback.
- Runtime scoring UI, input/mic settings, audio effects, minigames, LED
  indications and debug readouts. Core DSP, codecs and hardware interfaces
  remain native.
- Music database queries and test insertions: `MusicDatabase.lua` defines
  `DoSql` helpers, and `Main.lua` has an unused `AddCatalogDataForDebug()`
  function with `Music`/`ChartOnly` insert examples. This is useful schema
  evidence for a genuinely new song entry, not evidence that a text-only
  insertion makes a playable song.
- Default sequence names (`SequenceTrackConfig.lua`): Time, Conductor,
  Audio, Lyric, Melody, Group, Section, Led, CallAndResponse, Movie and
  AudioEffect. Its `chart:CreateSequence` calls show that an editor-facing
  native construction API existed; retail availability is unverified.

The scripts reveal *how the game invokes and displays* songs, but not the
complete IXB ownership/pointer layout, asset hashes, media decoding or all
requirements for registering a new catalog entry. They can narrow those
unknowns by observing native results; they do not replace the writer.

## Obsolete online features

`Menu/EntranceMenu2.lua` routes `GetMusic` to a storefront state.
`Main.lua` separately invokes native catalog-download and local DLC-install
states; `MyLipsMenu.lua` has online-user checks. If the original service is
unavailable, hiding the `GetMusic` entry and preventing its transition is
plausible at the script/UI layer *once script modification is proven active*.
That does not remove network code from the XEX or necessarily stop catalog
checks during startup. Do not disable `InstallDLC`, the local content database,
or chart/lyric lookup wholesale: these may also be needed by a standalone
custom song. Any offline-cleanup patch should be opt-in, isolated and tested
against existing disc songs and local DLC.

## Next verification gate

1. Completed for OG startup: retail opens `PackedScript.X360`, not loose Lua.
   Recheck later game states only if a loose-script fallback is suspected.
2. Identify a reversible way to instrument the active Lua package or its
   native call boundary. A source-file edit with no visible effect is not a
   passed gate.
3. On a known-good song, collect bounded load/playback timing diagnostics;
   compare the generated chart only after the same probe succeeds there.
4. Treat online UI cleanup as a separate optional mod after chart diagnostics.
