# Chart Root Minimal Crash Analysis

This report compares the original `full-current` hard crash with the new
`chart-root-minimal` crash.

Test result supplied from X360Debugger:

- variant: `chart-root-minimal`
- exception: `0xC0000005`
- new IAR: `0x82AB33A0`
- old IAR: `0x82AB3284`
- write target: `0x00000000`
- thread: `0xF9000000`

Local dump analyzed:

- `C:\Users\Gerrit\Desktop\dump.bin`
- size: `0x1110000` bytes
- image base: `0x82000000`

Generated local reports:

```powershell
py tools\analyze_x360_crash_dump.py C:\Users\Gerrit\Desktop\dump.bin `
  --iar 0x82AB33A0 `
  --write-target 0x0 `
  > private\outputs\crash_dump_report_chart_root_minimal.txt

py tools\analyze_x360_crash_dump.py C:\Users\Gerrit\Desktop\dump.bin `
  --iar 0x82AB3284 `
  --write-target 0x0 `
  > private\outputs\crash_dump_report_full_current_recompare.txt
```

The generated reports are under `private/outputs` and should not be committed.

## Address Comparison

Both crashes are in the same loaded game image and the same `.pdata` function.

| Crash | IAR | RVA | Function | Function offset | Unwind/info |
| --- | ---: | ---: | --- | ---: | ---: |
| `full-current` | `0x82AB3284` | `0x00AB3284` | `0x82AB2DD8-0x82AB3548` | `0x4AC` | `0x40003704` |
| `chart-root-minimal` | `0x82AB33A0` | `0x00AB33A0` | `0x82AB2DD8-0x82AB3548` | `0x5C8` | `0x40003704` |

Conclusion: this is not a different high-level chart loader function. It is
the same optimized PowerPC copy/move helper, reached through a different inner
copy path.

The new IAR is `0x11C` bytes after the old IAR inside the same helper.

## Old Crash Site

Old `full-current` crash:

```text
82AB3274: 80040004  lwz r0,4(r4)
82AB3278: 80E40008  lwz r7,8(r4)
82AB327C: 8104000C  lwz r8,12(r4)
82AB3280: 28060000  cmplwi cr0,r6,0
82AB3284: 90030004  stw r0,4(r3)  <-- old IAR
82AB3288: 84040010  lwzu r0,16(r4)
82AB328C: 90E30008  stw r7,8(r3)
82AB3290: 9103000C  stw r8,12(r3)
82AB3294: 94030010  stwu r0,16(r3)
```

The debugger reported write target `0x00000000`. For `stw r0,4(r3)`, the
effective destination was `r3 + 4`. If the effective address was zero, then the
destination register was likely:

- `r3 = 0xFFFFFFFC`

This is consistent with a copy helper receiving a null/invalid destination
pointer and entering a pre-adjusted word-copy loop.

## New Crash Site

New `chart-root-minimal` crash:

```text
82AB3378: 88E40004  lbz r7,4(r4)
82AB337C: 89040003  lbz r8,3(r4)
82AB3380: 38C6FFFF  addi r6,r6,-1
82AB3384: 5107442E  byte-pack/insert into r7
82AB3388: 89240002  lbz r9,2(r4)
82AB338C: 28060000  cmplwi cr0,r6,0
82AB3390: 5127821E  byte-pack/insert into r7
82AB3394: 89440001  lbz r10,1(r4)
82AB3398: 38840004  addi r4,r4,4
82AB339C: 5147C00E  byte-pack/insert into r7
82AB33A0: 90E30001  stw r7,1(r3)  <-- new IAR
82AB33A4: 38630004  addi r3,r3,4
82AB33A8: 4082FFD0  bne 0x82AB3378
```

This path loads individual bytes from the source and packs them into a word
before storing. That is an unaligned copy path, not the old aligned-ish
multi-word copy loop.

With write target `0x00000000`, the new faulting store implies:

- instruction: `stw r7,1(r3)`
- effective destination: `r3 + 1`
- likely `r3 = 0xFFFFFFFF`

So the immediate bad value is still the copy destination, not obviously the
source. The source bytes at `r4+1` through `r4+4` were read before the crashing
store, so the source pointer was at least readable at that point.

## Register And Stack Availability

The current dump is a PE/XEX-style image dump, not a full process memory dump.
It covers roughly:

- `0x82000000-0x83110000`

No new stack pointer was supplied with this crash report. The previous stack
pointer range, `0x30199850`, is outside this captured image range. Therefore:

- stack contents are not available from this `dump.bin`
- register values are not embedded in the dump in a form the current tool can
read
- `r3`, `r4`, `r5`, `r6`, `LR`, `CTR`, and `GPR1/SP` need to be captured from
  X360Debugger at crash time for a definitive source/destination trace

The only reliable register inference here is from the faulting store plus the
debugger's write target.

## What Changed

`chart-root-minimal` changed execution enough to enter a different copy path
inside the same helper:

- old path: word/multi-word copy, crashing at `stw r0,4(r3)`
- new path: unaligned byte-pack copy, crashing at `stw r7,1(r3)`

That strongly suggests the loader is now copying a different field, a different
length, or a differently aligned buffer than it did for `full-current`.

It does not mean the root graph is valid yet. The null write target means the
runtime still eventually passes a null/invalid destination to the helper.

## Chart Root Field Suspects

The current synthetic `chart-root-minimal` debug output is self-consistent:

- `ixChart.m_vpSequence` points at the synthetic sequence-vector reference
- `ixSequence.m_vpSeqCode` points at the synthetic seq-code-vector reference
- `lpsChart.m_pIndex` points at synthetic `lpsMusicIndex`
- `lpsChart.m_pMusicData` points at synthetic `lpsMusicInfo`
- the builder reports no invalid required pointer-like fields under its own
  synthetic reference map

But the crash suggests at least one of those fields is still runtime-invalid.

Highest-suspicion fields:

1. `ixVector<ixSequence *>`

   The synthetic chart uses a non-empty vector:

   - `data = 0x05001100`
   - `reserve = 32`
   - `size = 2`
   - entries: synthetic `ixTempoMap`, synthetic `ixSequence`

   If Lips expects a different file-layout encoding for vector backing storage,
   or cannot resolve the synthetic `0x05001100` reference as vector data, this
   can lead to a null destination during vector construction/copy.

2. `ixVector<ixSeqCode *>`

   The synthetic sequence uses a non-empty vector:

   - `data = 0x05001500`
   - `reserve = 32`
   - `size = 6`
   - entries: MelodyMarker/LyricMarker synthetic references

   This is the most obvious new count-bearing runtime path. A count greater
   than zero plus an unresolved or misencoded data reference is exactly the kind
   of shape that can reach an optimized copy helper with a bad destination.

3. `lpsChart.m_pIndex` and `lpsChart.m_pMusicData`

   The extended-layout corpus supports these fields, but the synthetic objects
   are deliberately minimal and mostly zero. If the loader assumes non-empty
   string/vector members inside `lpsMusicInfo` or `lpsMusicIndex`, or if the
   pointer/reference encoding is wrong, the loader can still construct an
   invalid copy destination.

4. Minimal `lpsMusicInfo` / `lpsMusicIndex` contents

   These objects are present because the extended chart layout points to them.
   However, they currently do not contain real URI/name string data like a
   corpus file. Empty fields alone are not proven fatal, but these are now
   active traversal targets and should remain on the suspect list.

## Interpretation

The new crash is progress in the diagnostic sense:

- `chart-root-minimal` changed the execution path
- the game likely traversed some part of the newly added root/sequence layer
- the failure remains a null/invalid copy destination inside the same helper

The best current explanation is:

> The chart root layer is being traversed, but one of the new non-empty
> vector/reference fields is still encoded in a way the runtime cannot resolve
> into a valid destination buffer.

This points more toward vector/reference encoding than toward MelodyMarker
timing, lyric text encoding, or lyric ownership.

## Next Data To Capture

Before adding more structures, the next useful Xbox-side capture is the full
register state at `0x82AB33A0`, especially:

- `r3`: copy destination cursor
- `r4`: copy source cursor
- `r5`: copy length or remaining byte count
- `r6`: loop counter / alignment count
- `r7`, `r8`, `r9`, `r10`: packed source bytes
- `r11`, `r12`: computed copy bounds
- `LR`: caller return address
- `CTR`: loop count
- `GPR1/SP`: stack pointer

If X360Debugger can dump memory around the new `GPR1/SP`, capture at least:

- `SP - 0x100` through `SP + 0x300`

The return address in `LR` and/or the stack would tell which chart field copy
called this helper.

## Next Minimal Test Ideas

Do not implement these until the register/stack evidence is reviewed.

Potential isolation variants:

- keep `lpsChart` and `ixSequence`, but set `ixChart.m_vpSequence.size = 0`
- keep the sequence vector, but set `ixSequence.m_vpSeqCode.size = 0`
- keep `ixSequence.m_vpSeqCode.size > 0`, but include only one seq-code entry
- keep chart root but set `lpsChart.m_pIndex` / `m_pMusicData` to zero
- keep `m_pIndex` only, then keep `m_pMusicData` only

These would isolate whether the null copy destination is triggered by the
sequence vector, the seq-code vector, or music metadata traversal.
