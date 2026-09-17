# Next Runtime Steps

## Confirmed Starting Point

Runtime Test 2 proved that a Lips-1 plain-IXB template accepts a complete
visible lyric-content replacement when decoded character positions, chart
WordData ranges, payload capacity, padding, file size, object graph, and
container fields remain unchanged.

The next work is split into two independent paths. They must not be deployed in
the same console test.

## Required Order

1. Restore unmodified Chart and Lyric files before testing Lua.
2. Debug Lua Test 1 produced no visible version text; record the result and
   restore the original Lua file.
3. Do not prepare Debug Lua Test 2 or enable controller debug commands from the
   loose source path.
4. Continue designing and reviewing the variable-layout Chart+Lyric patch.
5. Run the variable-layout test with the original, unmodified Lua files.

This order ensures that a Lua load failure cannot be mistaken for a Chart or
Lyric failure, and debug output cannot change the behavior of the first
variable-layout runtime test.

## Main Path: Variable Lyrics At Fixed Capacity

### Goal

Use genuinely different word and line lengths while preserving the template's
total lyric payload capacity and file size. Update existing chart
`LyricWordData.text_offset` and `text_length` values so each existing marker
selects the intended segment of the new text.

### Preserved State

- Lyric payload capacity and resource payload-length field.
- Existing prefix/BOM and observed trailing padding strategy.
- Chart and Lyric file sizes and IXB section boundaries.
- Marker count, marker timing, melody/pitch data, classes, object graph,
  pointer fields, hash-like field, and `NumOfElements`.
- All unknown bytes.

### Intended Changes

- Visible Lyric text bytes within the selected resource.
- Existing chart WordData `text_offset` and `text_length` fields only.
- No marker insertion, deletion, or record resizing.

### Preflight Requirements

- Define the new text and a one-to-one assignment for every retained lyric
  marker before writing bytes.
- Establish whether each WordData range counts decoded characters or UTF-8
  bytes. Use ASCII-only input for the first variable-layout test if this remains
  ambiguous.
- Reject text that exceeds the existing payload capacity.
- Verify every new range is non-negative and ends within decoded visible text.
- Account for repeated tracks/markers explicitly rather than deduplicating by
  timing alone.
- Fill unused payload capacity with the template's existing padding byte and
  preserve the total stored payload length.

### Exact Diff Whitelist

The Lyric diff may contain only the selected visible payload range plus its
existing padding range. The Chart diff may contain only known WordData
`text_offset` and `text_length` 32-bit fields for existing markers.

Any change to headers, classes, section tags, marker timing, pitch, pointers,
object ids, resource hash/length fields, or file size must fail validation and
block console deployment.

### Runtime Success Criteria

- Game and song load normally.
- New text and intended line layout are visible.
- Each highlighted syllable/word corresponds to its planned marker range.
- Timing, notes, pitch behavior, and marker count remain unchanged.
- Rollback restores both original Chart and Lyric files.

## Side Path: Lua Debug Mode

### Debug Lua Test 1

Patch only the readable Lips-1 `Main.lua` in `App:Launch()`, immediately after
`DebugSettings:InitializeDebugSettings()`:

```lua
DebugSettings.bVersionText = true
```

Expected proof: the later lobby/play initialization calls `ShowVersionText()`
and visible version text appears. In-game debug commands remain disabled.

Runtime result: no visible version text appeared. Local inspection found a
compressed `PackedScript.X360` asset, and the readable startup source refers to
the already loaded `PackedScript` package before unloading it later. The
strongest current interpretation is that retail startup uses the packed asset
instead of the loose source file.

### Optional Debug Lua Test 2

Blocked. Test 1 did not visibly succeed. The following override remains a future
concept only and must not be deployed from the loose source path:

```lua
DebugSettings.bVersionText = true
DebugSettings.bEnableInGameDebugCommands = true
```

Then test, in a Lua-only runtime session:

- `SELECT + RUP`: global debug menu or in-game input-device debug mode,
  depending on active state routing.
- `SELECT + RLEFT`: in-game chart/debug text toggle.

The duplicate `SELECT + RUP` handlers make the exact active behavior a runtime
question. Do not enable other debug flags in the first command test.

### Debug Risks And Stop Conditions

- No version text means the file may not be loaded from the tested game path;
  stop before enabling commands.
- A Lua error, freeze, or failed startup requires immediate rollback.
- Do not patch `.luaB`, XEX, binaries, Chart, or Lyric files to diagnose Test 1.
- Use Ghidra only if the readable Lua path is confirmed but the minimal override
  still fails for a concrete native-side reason.

Current stop decision: restore the original Lua file and continue the main
Chart+Lyric path. If debug mode becomes necessary later, ask one targeted native
question: whether retail startup always sources `PackedScript.X360` and whether
a loose-script fallback can be enabled without binary modification.

## Deferred Work

- Payload growth beyond the template capacity.
- Marker insertion/removal and object-vector rebuilding.
- Melody/pitch editing in the same test as variable lyrics.
- Audio-reference or audio-stream replacement.
- Later/DLC, LS2, compressed, `.luaB`, Binary, or XEX patching.
