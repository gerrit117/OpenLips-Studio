# OG XEX reverse-engineering strategy

Status: 2026-09-30. Research targets the user's private OG 2008 executable.
No executable, script package, decompiled source, or game assets are included.
The primary objective remains a standalone UltraStar-to-Lips song builder,
not a modified game executable.

## Was XEXLoaderWV applied correctly?

Yes for this executable and the current evidence. The private OG import used
Ghidra 12.1.3 with the supplied XEXLoaderWV extension built for 12.1.3,
selected the loader's PowerPC:BE:64:A2ALT-32addr language, and processed
`.pdata` without requesting a PDB. The import log identified XEXLoaderWV,
created 43,179 initial `.pdata` functions and named 361 import thunks. The
subsequent audit checked all 102 normal-compression block hashes, produced the
declared 18,546,688-byte image, and found 15/15 inspected imported image
blocks byte-identical. See `og_ghidra_setup.md` and
`og_loader_validation.md` for the exact scope and caveats.

The current [XEXLoaderWV README](https://github.com/zeroKilo/XEXLoaderWV)
recommends turning off `Process .pdata` only when importing a PDB/XDB using
its experimental loader and MSDIA. No PDB was available for this retail game,
so that instruction does not invalidate the existing import. A newer
SaveEditors-maintained revision mentions `.pdata` function-creation fixes;
the local result already has real functions, and an upgrade alone is not a
plausible cure for the observed decompiler problems.

The major remaining Ghidra limitation is analysis, not evidence of a missing
plugin: PowerPC save-register helper calls were falsely treated as no-return.
Read-only callfixup experiments recovered substantial IXB-reader pseudocode.
Many native functions still lack trustworthy boundaries, argument types,
virtual-call targets or meaningful names. The 300-second initial automatic
analysis limit is not a claim of full program decompilation.

## Lua-specific audit

`tools/ghidra/StudyOgLuaLoad.java` checks the exact OG executable hash and
searches script-related literals, automatic xrefs and a bounded set of
decompilations. It is read-only and writes its report only to a private path.
It found `PackedScript/`, `require( "Script/Main" )`, `LPS_LUA_RELEASE`, and
Lua search-path strings. The only automatic `PackedScript` xref is in code
whose containing function was not reconstructed; other strings have no
automatic xrefs. These are anchors for targeted call-graph repair, not proof
that setting `LPS_LUA_RELEASE=0` changes script-source selection. The Xenia
file-open trace establishes that the retail startup opens the packed package
and did not open loose `.lua` files in the observed interval.

## Tool choice

- Ghidra + XEXLoaderWV: primary static tool for named imports, strings,
  PowerPC pseudocode, `.pdata` boundaries, class layouts and targeted call
  graphs. Reconstruct IXB reader, script loader, chart clock and sequence
  initialization; validate each claim in Xenia.
- Xenia guest debugger and bounded instrumentation: primary dynamic tool for
  comparing original and generated charts at the same native function or
  object field. Avoid broad logging that makes playback unresponsive.
- [XenonRecomp / XenonAnalyse](https://github.com/hedge-dev/XenonRecomp):
  potentially useful as a secondary function-boundary/jump-table cross-check.
  Its output is register-state C++, explicitly not human-readable decompiled
  game logic, and no runtime is supplied. Its current documented MMIO and
  exception gaps make a full Lips port a separate, much larger project.

No tool can guarantee that every relevant stripped retail function is
automatically named or semantically understood. We can define the functions
needed for song loading through evidence-driven type and call-graph recovery.
The immediate runtime question is why a valid-looking fresh chart displays
notes but its chart clock does not advance. The v6 root-hash test ruled out
one isolated field change. The next probe should compare original Amazing and
the fresh chart at native chart-start/tempo-map/sequence-update boundaries,
then change one proven differing field family at a time. A packed-Lua edit is
not a prerequisite for that comparison.
