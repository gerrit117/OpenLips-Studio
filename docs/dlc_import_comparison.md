# OG DLC import comparison

Read-only investigation, 2026-10-01. The custom STFS is enumerated but its song
is not visible. Do not equate successful container verification with successful
Lips DLC installation. No emulator configuration, game files, profile or
installed package was modified during this comparison.

## Corpus

All four original containers found directly in the private `Songdateien/DLCs`
directory were extracted for analysis into a separate private directory.
They contain six MusicIndex entries. All URI references resolve to contained
files case-insensitively. No `spa.bin` occurs in any of these four packages.
The loose, previously edited top-level DLC.xml is not a reference.

Analyzed container filenames:

| Original container | Songs | Chart family |
|---|---:|---|
| 00031550837D8EEFEAC978CAEE3B97F3F217154F4D | 3 | extended/later |
| 00C11F2EEFCB355A460A076EF8F4A9B1D084C8774D | 1 | extended/later |
| 01865DC82B361FC4C3305CB98B80B45B5E569BBA4D | 1 | extended/later |
| 02E5D2FACD95401040150713774FA36330787D404D | 1 | compact OG |

These family labels are based on schema layouts, not a claim that every
reference package works in the unupdated OG executable. The compact-family
sample is one file only and therefore low-confidence DLC gameplay evidence.

## Measured differences

| Field/pattern | Originals | Custom | Confidence in observed pattern |
|---|---|---|---|
| Magic / TitleID / content type | LIVE / 4D530888 / 2, 4/4 | same | high within corpus |
| Header size / metadata version | 0xAD0E / 2, 4/4 | same | high within corpus |
| ProfileID | zero, 4/4 | zero | high within corpus |
| Single-copy volume flag | 1, 4/4 | 1 | high within corpus |
| Platform | 0, 4/4 | 2 | high within corpus; runtime significance unknown |
| Header content size | file size minus rounded header, 4/4 | sum of embedded file lengths | high within corpus; runtime significance unknown |
| Package filename | 42 hexadecimal characters, no extension, 4/4 | descriptive name with .LIVE | high within corpus; game requirement not proven |
| Filename first 40 digits equal header SHA-1 | 3/4 | no | medium; not invariant |
| Filename suffix | 4D, 4/4 | .LIVE | high within corpus; game requirement not proven |
| DLC.xml UTF-8 BOM | present, 4/4 | absent | high within corpus; parser requirement not proven |
| Nonempty PreviewLyric | 6/6 MusicIndex entries | empty | high within corpus; requirement not proven |
| MusicVideos group | present in 2/4 manifests | present | medium; not universal |
| PreviewVideoUri and PreviewIconUri | 4/4 video entries in those 2 packages | absent | medium; requirement not proven |
| MusicVideo identity member | ID in 3 entries, ChartID in 1 | ChartID | varies; do not standardize from one sample |
| LicenseBits XML element | present in 3/4 manifests | present | medium; not universal |
| Header license records | bits=1; active flags vary | bits=7, flags=1 | varies; originals may have been license-modified |

The custom manifest contains all 19 field names present in 6/6 MusicIndex
entries. Every generated URI resolves to a file in the package. TitleID and
resource existence alone do not validate the game's catalog semantics.

Structural chart comparison:

- Extended layout, 5/6: ixChart=108, lpsChart=184, MelodyMarker=40 bytes.
- Compact layout, 1/6: ixChart=92, lpsChart=148, MelodyMarker=36 bytes.
- Custom: compact sizes 92/148/36, 780 melodies and 2,526 objects.
- ixSequence=104 bytes in all 6/6 originals and custom.

This supports keeping the runtime-accepted OG writer unchanged. It does not
justify copying extended-chart roots into an OG DLC candidate.

## Runtime and native import evidence

Observed Xenia log:

1. XamContentCreateEnumeratorInternal adds the custom package to its result.
2. Lips starts DLC::InstallThreadProc0.
3. The STFS device is accessed, including an optional spa.bin lookup.
4. In the inspected startup trace, there is no logged DLC.xml resolution.

The spa.bin lookup is made by Xenia's ContentManager::OpenContent; an absent
file is explicitly permitted. It is not evidence of a required missing file.
The unsigned signature did not prevent enumeration or STFS access. Do not
change license_mask blindly based on this observation.

Read-only Ghidra analysis of the verified OG executable used the existing
PowerPC save-register-helper repair. An unrepaired decompilation terminated
incorrectly at the function prologue and was discarded as unusable evidence.
Executable SHA-256:
`95f32d3de1f80a85dd2faedc4e88f4bf7e218606051c1b2971d17c35a0b7e4d9`.

Relevant bounded functions:

- 0x82D0A0F8: enumerated-content installation path, requests a package owner
  through 0x82D0EF58, then invokes 0x82D06F48.
- 0x82D06590: copies the 42-byte XCONTENT filename, forms `DLC%s` as mount
  name, creates the package-opening object and requests synchronous opening.
- 0x82D04928: invokes XamContentCreateEx through 0x8280DD18; marks the owner
  state as 3 after successful synchronous opening.
- 0x82D06F48: requires a non-null owner in state 3 before constructing the
  DLC.xml path and parsing DLCContents/MusicIndices.
- 0x82D06800: builds the manifest/resource path from the owner's mount name.
- 0x82379F58: XML acquisition/parsing dispatch; whether failure occurs here
  or earlier is not determined by the current log.

Function types remain provisional; these addresses are specific to the
verified build. Static analysis proves branch structure, not values observed
in the failing runtime. Missing log entries alone do not prove that the
manifest function was never entered.

## Conclusion and controlled next tests

**The exact rejection condition is still unresolved.** The comparison rules
out basic absence of the package and missing named chart/audio/lyric assets,
but does not prove retail authenticity, game-level validation or catalog
insertion. No builder serialization changes were made just to match patterns.

Next investigate the pre-manifest boundary rather than rebuild the IXB graph:

1. Record XamContentCreateEx return value, generated mount name and the owner
   state at entry to 0x82D06F48; record the final path and XML return value.
2. Run one unmodified compact-family reference DLC in the same emulator/profile
   as a control. Do not infer OG compatibility from the five extended charts.
3. Test a **byte-identical package with a 42-hex-character extensionless name**
   separately from all other changes. This isolates pathname handling.
4. If the manifest is reached, test UTF-8 BOM separately, then catalog-field
   and video/preview requirements. Header platform and content-size conventions
   are additional isolated tests, not simultaneous speculative fixes.

Keep the accepted independent disc song and earlier DLC files as rollback
references. Do not erase a profile to hide an import failure.

A private name-only candidate was prepared outside the installation in
`private/outputs/dlc-name-test/`, using header-SHA-1 plus `4D` as the filename.
Its full SHA-256 equals the descriptive-name candidate:
`018b6850723a4143aceae37fa3e971c9c06e3b0c299474f048bd8125bbe1e559`.
No bytes changed. This is a prepared test, **not a confirmed fix**. Install
only one of those duplicate-content names during a test, never both together.

## Reproduce

`tools/analyze_dlc_packages.py` reads STFS headers and separately extracted
manifests, resolves URI coverage and summarizes structural chart families.
It prints JSON to stdout and does not modify source files:

```text
py tools/analyze_dlc_packages.py --originals private/original-dlc --extracted private/extracted-dlc --custom private/custom.LIVE --custom-extracted private/extracted-custom
```

Use the backend's extract command into new private directories first.
`tools/ghidra/StudyOgDlcInstall.java`, run with headless `-readOnly -noanalysis`,
locates bounded string-reference candidates and delegates repaired function
decompilation to StudyOgIxbReader.java. Private disassembly/decompilation and
original XML/media are not committed; only sanitized findings and tooling are.
