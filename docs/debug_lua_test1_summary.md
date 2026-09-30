# Debug Lua Test 1 Summary

## Scope

- Role: isolated Lua loading/override test.
- Target family: readable Lips-1 Lua scripts.
- Patch location: `App:Launch()`, immediately after
  `DebugSettings:InitializeDebugSettings()`.
- Added runtime override: `DebugSettings.bVersionText = true`.

No song data, Chart, Lyric, binary, XEX, or `.luaB` file is modified. Controller
debug commands are not enabled in this test.

## Expected Result

Visible version text should appear when the lobby/play initialization checks
`DebugSettings.bVersionText`. This is proof that the tested readable Lua file is
loaded and that a post-initialization override survives the release defaults.

## Runtime Result

No visible version text appeared. The controller-command override was not
enabled, so the result is isolated to the readable Lua loading question.

Local follow-up found a compressed `PackedScript.X360` asset. The readable
startup script itself refers to an already loaded `PackedScript` package and
unloads it later in startup. This is strong evidence that the retail runtime
executes startup code from the packed asset rather than the loose readable
source. Native load-path confirmation is still pending, so this remains a
strong indication rather than a proven fact.

Update, 2026-09-30: an isolated Xenia `NtCreateFile` trace observed
`game:\lps\Assets\PackedScript.X360` and no loose `.lua` opens among 532
file-open attempts through the OG title screen. The packed startup load is
now directly observed for that path; see `lua_runtime_capabilities.md`.

## Validation

- Original source encoding retained byte-for-byte outside the inserted block.
- CRLF line endings preserved.
- Backup is byte-identical to the private source file.
- Patched copy contains exactly one additional version-text assignment.
- `bEnableInGameDebugCommands = true` is absent.
- A reverse application of the inserted block reproduces the original bytes.

## Follow-Up Gate

The gate was not passed. Do not prepare or run a separate Debug Lua Test 2 with
`bEnableInGameDebugCommands = true` from the loose source file.

The remaining concrete question is whether retail startup always loads
`PackedScript.X360` and whether a supported loose-script fallback exists. This
can be answered later through a narrowly targeted native load-path analysis.
Do not patch `.luaB`, `PackedScript.X360`, Binary, or XEX files meanwhile.
