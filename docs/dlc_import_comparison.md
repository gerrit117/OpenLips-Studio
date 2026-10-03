# OG DLC import comparison

Investigation started 2026-10-01, with isolated runtime follow-up on 2026-10-02.
The custom STFS is enumerated but its song is not visible. Do not equate
successful container verification with successful Lips DLC installation.
The initial comparison was read-only; subsequent emulator/configuration changes
and generated saves are confined to a separate private test directory. Original
game files, packages, user profiles and normal emulator storage remain untouched.

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

### Isolated runtime control, 2026-10-02

An isolated Canary storage directory was used with one byte-identical original
compact-family DLC and the extensionless, name-only Shape of You candidate.
Only the existing offline profile identity was copied; the user's existing Lips
save and normal emulator content directory were not changed. Computer Use reached
the main menu, which still displayed 40 disc songs for both control runs.

Read-only diagnostics in the local emulator established:

- Both packages are returned by content enumeration.
- Both `XamContentCreateEx` calls return `0x00000000` synchronously, flags
  `0x13`, with distinct `DLC` plus 42-character filename mount names.
- Both subsequently open `DLC.xml`. The compression-information diagnostic now
  prints the XFile path, which is `DLC.xml` for both packages.
- The earlier STFS ResolvePath trace printed the parent lookup (empty for a root
  file), not necessarily the opened file's name. Consequently, absence of a
  ResolvePath line spelling `DLC.xml` must **not** be treated as absence of access.
- The unimplemented compression query also occurs on normally loaded disc
  assets. Its presence alone does not establish the cause of DLC rejection.

Thus naming, package enumeration and immediate mounting have been exercised;
catalog insertion remains unconfirmed. A failing original control prevents
attributing the current failure exclusively to the custom builder. The next
probe records XML read status, length and a bounded prefix without changing
guest execution or any package bytes.

Subsequent read-only probes confirmed full XML delivery (1,120 bytes for the
original, 1,310 for custom), status `0x00000000`. Native OG instruction probes
showed XML parse success (`r3=1` after 0x82379F58), non-null DLCContents and
MusicIndices lookups, and a non-null parsed MusicIndex in **2/2 tested packages**.
This narrows this runtime failure to a later catalog/eligibility stage rather than
missing XML, malformed XML prologue or immediate package mount failure.

The same isolated offline profile was tested with Canary `license_mask=0` and
`license_mask=7`, keeping packages and storage unchanged. Both runs displayed
40 songs, including after the in-game signed-in notice was dismissed. There
was no `NO_SUCH_USER` result in the traced package-open calls. This does not
prove all profile/license paths are correct, but changing the global mask alone
did not fix visibility. A local sign-in must not be equated with Xbox Live sign-in.
Unimplemented controller force-feedback exports and compression-info queries
occur during normal startup and must be separated from proven DLC blockers.

### Profile gate and catalog entry probes

The later bounded native trace establishes the following for **2/2 packages**
(one unchanged official compact-family DLC and one custom song):

- At `0x82D0A248`, the manifest/import operation returns zero.
- The selected local player is index zero, with a non-null user context.
- At `0x82D0A2B8`, the user-context eligibility flag is one.
- At `0x82D0A2C4`, the parsed MusicIndex count is one.
- `0x82D231F8`, the catalog-insertion routine, is entered for each MusicIndex.

Entering that routine is **not** proof that a database row was successfully
inserted or that the song passed the later availability filter. Its database
context lookup at `0x82D49E60` can return null and short-circuit insertion;
SQL execution through `0x82D4B888` and subsequent availability processing at
`0x82D1F9E0` remain unmeasured. The next diagnostic boundary is inside catalog
insertion, not before manifest parsing. The user's additional official-DLC
failure is a separate report, not an additional instrumented sample.

### Xenia documentation and issue review, 2026-10-02

Scope: Master (`xenia-project/xenia`), Canary (`xenia-canary/xenia-canary`)
and AdrianCassar's Canary Netplay. Netplay was included because the Lips
compatibility report itself links to that fork; it is not asserted to be
installed locally. This is a documentation/source review, **not** a successful
three-build runtime comparison.

| Finding | Evidence and confidence | Relevance to this test |
| --- | --- | --- |
| Different installation formats | High: [official Quickstart](https://github.com/xenia-canary/xenia-canary/wiki/Quickstart) distinguishes Canary Install Content from Master extracted DLC folders. | Do not apply one fork's installation instructions to every build. Both current Canary packages already mount and deliver XML. |
| Matching title update | High for the general recommendation: [Manager troubleshooting](https://xenia-manager.github.io/wiki/help/troubleshooting/) recommends the matching TU before DLC. Low for this specific Lips failure: no controlled TU comparison yet. | Current test has Media ID `39B3E0C9`, Title ID `4D530888`, and no verified applied TU. A search of the project private tree and Desktop Lips filenames found no obvious TU container; localized `TU02_ranking.nft` textures are not title updates. Match Media ID and base executable version, not Title ID alone. |
| Package versus extracted content | High: the same troubleshooting page recommends extracted mode when package support differs between builds. | Still an untested isolation axis. Preserve package name and metadata and use a separate storage root, not duplicate representations in the same installation. |
| Wrong storage root/config | High: Manager documents independent variant configs and unified/per-emulator content paths. | Unlikely to explain this measured run: the expected packages are actually enumerated, opened and parsed. It can still explain a separate user test. |
| Common-content enumeration regression | High: [Canary PR 613](https://github.com/xenia-canary/xenia-canary/pull/613) fixes incorrectly excluding shared content when no XUID exists. | Corrected condition is present in the local source (`!xuid` or no exclude-common flag). Both packages enumerate, so this is not the observed stopping point. |
| Local versus Live sign-in | High for source behavior; low as a cause of this failure. [Netplay source](https://github.com/AdrianCassar/xenia-canary/blob/6dbaa1fefd1e07cc3d5377e763c68fe8073cbe8c/src/xenia/kernel/xam/user_profile.cc) reports Live only for a Live-enabled profile in XboxLive network mode. | Netplay sign-in emulation differs from ordinary Canary; it is not access to Microsoft's official Xbox Live. Local sign-in and the measured Lips import gate already work. No evidence yet that DLC requires Live sign-in. |
| Lips database initialization reports | Medium: [compatibility discussion](https://github.com/xenia-canary/game-compatibility/issues/1119#issuecomment-4642790898) reports increased song counts after Xbox databases were copied into Xenia. | Supports investigating the catalog, but is an anecdote involving a modified multi-game setup, not proof that copying databases is a safe fix. Do not overwrite the user's saves. |
| XMP startup fix | High: [PR 1042](https://github.com/xenia-canary/xenia-canary/pull/1042) returns success for zero media sources and was merged June 6, 2026. | Relevant to OG startup stability; no demonstrated fix for DLC catalog visibility or later LS2 startup. USB-microphone support remains separate. |

The local diagnostic build is based on Canary commit
`aee0871dd7a783de7ec61dfbd5e9985977093025` (September 16, 2026), with
read-only diagnostic additions. Older reports such as
[Canary issue 21](https://github.com/xenia-canary/xenia-canary/issues/21) and
[Master issue 2154](https://github.com/xenia-project/xenia/issues/2154) establish
historical DLC/TU regressions, not that this current build has the same bug.
The older Canary FAQ's folder examples should not override current Quickstart
or the storage root actually used by the process.

The Quickstart says Install Content applies licenses automatically. In the
local revision, read-only STFS installation copies the container and broadcasts
a content-installed notification; it does not visibly rewrite its licenses in
that installation path. `ComputePackageLicenseMask` exists but a source-wide
search found no call sites. This is a source concern to measure, not proof of
the failure. Global mask zero versus seven already produced identical 40-song
results; do not present setting all bits as a confirmed solution.

Prioritized controlled follow-up:

1. Inspect the **isolated** MusicDB and GameContentDB read-only for the official
   and custom IDs, then measure database-context lookup, SQL result and visibility
   filtering. Separate no insertion from insertion followed by hidden status.
2. Compare one official DLC as container versus extracted content, with separate
   storage roots, the same profile identity and no edits to package contents.
3. If a legally obtained, matching TU is available, verify actual application in
   the log before testing it. Do not force an incompatible update. Probe addresses
   above apply only to the verified unupdated executable and must be relocated
   for a TU.
4. Compare a clean released Canary with the diagnostic build. Use Netplay only
   as a separate profile/API comparison, without enabling remote services or
   converting the user's normal profile. Master is a secondary control because
   its older Lips report stops at the microphone/menu path.

No documentation or issue reviewed establishes a universal Lips DLC fix.
Neither the official-control failure nor the docs justify speculative changes
to the Studio builder, original game files, licenses or existing saves.

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
