# Ghidra findings for Lips X360 / IXB loading

Date: 2026-07-03

Scope: currently opened Ghidra program `default.exe`, identified by the Ghidra MCP server as the extracted executable from the Xbox 360 Lips `default.xex`.

## Method

Ghidra was queried through the local MCP HTTP bridge at `127.0.0.1:8089`.

Used MCP capabilities included:

- open program and metadata inspection
- analysis status inspection
- segment, entry point, import, export and symbol listing
- string searches for the requested terms
- string cross-reference queries
- decompilation and disassembly around interesting addresses
- direct memory reads for string table ranges
- a custom PowerPC `lis` + `addi` / `ori` string-load scan, because many string references were not present as normal Ghidra xrefs

No functions were renamed during this pass.

## Program status

Confirmed facts:

- Open program: `default.exe`
- Executable path reported by Ghidra: `/Users/gerritsiepmann/Documents/default.exe`
- Format: `Portable Executable (PE)`
- Language: `PowerPC:BE:32:default`
- Compiler spec: `default`
- Image base: `0x82000000`
- Address range: `0x82000000` to `0x82f53157`
- Function count: `18406`
- Symbol count: `34630`
- Analysis status: analyzed, not currently analyzing

Main memory blocks:

| Block | Range |
| --- | --- |
| `Headers` | `0x82000000` - `0x820005ff` |
| `.rdata` | `0x82000600` - `0x82190c5f` |
| `.pdata` | `0x82190e00` - `0x821d1caf` |
| `.text` | `0x821e0000` - `0x82b697ff` |
| `.data` | `0x82bd0000` - `0x82e93bdb` |
| `.XBMOVIE` | `0x82e93c00` - `0x82e93c07` |
| `.idata` | `0x82ea0000` - `0x82ea05ff` |
| `.XBLD` | `0x82eb0000` - `0x82eb01ff` |
| `.reloc` | `0x82eb0200` - `0x82f53157` |

Entry/import/export facts:

- Program entry: `0x82000000`
- Exported entry function: `0x828dae18`
- Imports are mostly unresolved; Ghidra only reported one external stub-like import, `EXT_FUN_3baeafab` at `EXTERNAL:00000001`
- Export table only reported `entry -> 0x828dae18`

Namespaces and symbols:

- No useful application namespaces were recovered.
- Most named namespaces are switch-related or RTTI/type-info-like.
- Many useful functions are still named `FUN_...`.

## Requested string search results

The table below lists the relevant hits from the requested searches. It is not a full dump of all generic hits, because terms like `ix`, `file` and `hash` produce many unrelated engine/framework strings.

| Address | String | Notes |
| --- | --- | --- |
| `0x8200b378` | `%s_Lyric.ixb` | Lyric IXB filename format string. No reliable code xref found yet by Ghidra xrefs or the simple PPC string-load scan. |
| `0x8200b388` | `%s_Lyric` | Loaded by code near `0x822347b8`, `0x8223541c`, `0x8223550c`. Likely lyric path/name construction. |
| `0x82000b7c` and many others | `eIX_PLATFORMID_X360` | X360 platform enum/class metadata; many occurrences. |
| `0x8206d364` | `UseCompressToolForX360` | Compression/build option string. Loader connection not confirmed. |
| `0x8206d37c` | `bUseCompressToolForX360` | Compression/build option string. Loader connection not confirmed. |
| `0x820187e0` | `UPDATE Music SET ... ChartUri ... LyricUri ... AudioUri ... ChartContentFilename ...` | Music DB schema/update string; confirms database fields for chart, lyric and audio paths. |
| `0x8201ec40` | `CREATE TABLE IF NOT EXISTS LPS_MDB.Music (... ChartUri, LyricUri, AudioUri, ... FogID )` | Music DB schema creation string. |
| `0x82073d04` | `32ndNotesPerMidiQuarterNote` | MIDI timing field metadata. |
| `0x82073d20` | `m_32ndNotesPerMidiQuarterNote` | MIDI timing member metadata. |
| `0x82073d6c` | `MidiClocksPerMetronomeClick` | MIDI timing field metadata. |
| `0x82073d88` | `m_MidiClocksPerMetronomeClick` | MIDI timing member metadata. |
| `0x8200b310` | `m_strLyricPathCash` | Lyric path cache member metadata. |
| `0x8200b324` | `LyricPathCash` | Lyric path cache metadata. |
| `0x8200b288` | `m_strAudioEffectPresetPath` | Audio-related member metadata. |
| `0x8200b2a4` | `AudioEffectPresetPath` | Audio-related metadata. |
| `0x820561f0` | `OpenFile` | File-related script/reflection string. Caller not confirmed. |
| `0x820561fc` | `OpenInputFile` | File-related script/reflection string. Caller not confirmed. |
| `0x8205620c` | `OpenOutputFile` | File-related script/reflection string. Caller not confirmed. |
| `0x820615d4` | `[FileIO ERROR]: Tag doesn't match...(Expected: %s, Read %s)\n` | Used by header/tag validation function `FUN_8249fe28`. |
| `0x82061614` | `[FileIO ERROR]: Name doesn't match...(Expected: %s, Read %s)\n` | Used by header/name validation function `FUN_8249fed0`. |
| `0x82061658` | `[FileIO ERROR]: Version doesn't match...(Expected: %d, Read %d)\n` | Used by header/version validation function `FUN_8249ff68`. |
| `0x820622cc` | `"ixSerializerReader::Load"` | Source/assert string used in the IXB/XML reader candidate around `0x824acff0`. |
| `0x820622e8` | `.\Serialize\ixSerializerReader.cpp` | Source file string used in the IXB/XML reader candidate around `0x824acff0`. |

Searches for `wem`, `stfs` and `checksum` produced no useful literal string hits in this executable. Search for `xma` mostly matched unrelated substrings such as matrix/type names. Search for `sha` / `hash` mostly matched graphics or generic hash-table strings and did not yet identify song/package verification code.

## IXB serializer string table

Confirmed strings near the reader string table:

| Address | String |
| --- | --- |
| `0x82062243` | ` Class` |
| `0x8206224c` | `Size` |
| `0x82062254` | `Base` |
| `0x8206225c` | `UriList` |
| `0x82062264` | `Key` |
| `0x82062268` | `Objects` |
| `0x82062270` | `</Ob` |
| `0x82062278` | `NFT` |
| `0x8206227c` | `IsBigEndian` |
| `0x82062288` | `NumOfElements` |
| `0x82062298` | `Classes` |
| `0x820622a0` | `DDS` |
| `0x820622a4` | `ixb` |
| `0x820622a8` | `Member` |
| `0x820622b0` | `Members` |
| `0x820622b8` | `Name` |
| `0x820622c0` | `Offset` |
| `0x820622c8` | `Uri` |
| `0x820622cc` | `"ixSerializerReader::Load"` |
| `0x820622e8` | `.\Serialize\ixSerializerReader.cpp` |

Confirmed writer-side XML token strings:

| Address | String |
| --- | --- |
| `0x82061dcc` | `</Objects>` |
| `0x82061dd8` | `<Objects>` |
| `0x82061e1c` | `</Classes>` |
| `0x82061e3c` | `<Class` |
| `0x82061e50` | `<Members>` |
| `0x82061e5c` | `<Member` |
| `0x82061e8c` | `</Members>` |
| `0x82061e98` | `</Class` |
| `0x82061ea8` | `<Classes>` |
| `0x82061eb8` | ` NumOfElements="%d"` |
| `0x82061edc` | ` IsText="false"` |
| `0x82061eec` | ` IsBigEndian="%s"` |

## Important functions and code regions

### FileIO header validation

Confirmed facts:

- `FUN_8249fe28`
  - Address: `0x8249fe28`
  - Compares 4 bytes at `param_1 + 0x10` against an expected tag string.
  - On mismatch, formats `[FileIO ERROR]: Tag doesn't match...(Expected: %s, Read %s)\n`.
  - Returns `0` on success and `&DAT_82000101` on mismatch.

- `FUN_8249fed0`
  - Address: `0x8249fed0`
  - Compares 4 bytes at `param_1 + 0x14` against an expected name string.
  - On mismatch, formats `[FileIO ERROR]: Name doesn't match...(Expected: %s, Read %s)\n`.
  - Returns `0` on success and `&DAT_82000102` on mismatch.

- `FUN_8249ff68`
  - Address: `0x8249ff68`
  - Reads a 16-bit value from `param_1 + 0x18`.
  - If the stored value is greater than the expected version argument, formats `[FileIO ERROR]: Version doesn't match...(Expected: %d, Read %d)\n`.
  - Returns `0` on success and `&DAT_82000103` on mismatch.

Hypothesis:

- These functions validate a common binary resource/file header used by engine file formats.
- The observed object/header layout is probably:
  - `+0x10`: 4-byte tag
  - `+0x14`: 4-byte name
  - `+0x18`: 16-bit version
  - `+0x1a`: another 16-bit field, because adjacent accessors touch this offset
- It is not yet proven that this header is the outer `.X360` or IXB container header. It may also be a nested engine chunk header.

### IXB/XML writer region

Confirmed facts:

- Code around `0x824aaa68` to `0x824ab6f0` loads and emits XML-like serializer tokens including `<Classes>`, `<Objects>`, `<Member`, `NumOfElements`, `IsText` and `IsBigEndian`.
- Representative string-load/use addresses found by the PowerPC scan:
  - `<Classes>`: loaded near `0x824aab38`, used near `0x824aab40`
  - ` NumOfElements="%d"`: loaded near `0x824aab10`, used near `0x824aab18`
  - ` IsText="false"`: loaded near `0x824aaae0`, used near `0x824aaae8`
  - ` IsBigEndian="%s"`: used near `0x824aaad8`
  - `</Classes>`: used near `0x824ab26c`
  - `<Objects>`: used near `0x824ab320`
  - `</Objects>`: used near `0x824ab6f0`

Hypothesis:

- This is a generic IX serializer writer, not the song loader itself.
- It is still useful because it confirms the expected XML token names and writer-side structure.

### IXB/XML reader candidate

Confirmed facts:

- Code around `0x824acff0` references both:
  - `0x820622cc`: `"ixSerializerReader::Load"`
  - `0x820622e8`: `.\Serialize\ixSerializerReader.cpp`
- The same region references reader-side tokens:
  - `Class`
  - `Size`
  - `Base`
  - `UriList`
  - `Key`
  - `Objects`
  - `IsBigEndian`
  - `NumOfElements`
  - `Classes`
  - `Member`
  - `Members`
  - `Name`
  - `Offset`
  - `Uri`
- Disassembly shows repeated byte/string comparisons against these tokens and loop-like traversal over parsed nodes.
- Ghidra did not produce a useful decompile for this region because function boundary/prologue analysis appears confused around helper calls such as `FUN_82abff60`.

Hypothesis:

- The code beginning around `0x824acff0` is the generic `ixSerializerReader::Load` implementation or its main body.
- This function likely parses the XML metadata/header part of IXB-like serialized assets: classes, members, object list, offsets, URI lists and endian/element-count attributes.
- Helper calls in this block are likely XML/node helpers, but this still needs confirmation:
  - `0x824b2cf8`: likely find/get child or attribute by token name
  - `0x824b3c50`: likely node iteration or current-node access
  - `0x82ac22b8`: likely text/number/string conversion or copy helper

### Lyric path / song content path region

Confirmed facts:

- `%s_Lyric` at `0x8200b388` is referenced by code near:
  - `0x822347b8`
  - `0x8223541c`
  - `0x8223550c`
- The literal `%s_Lyric.ixb` at `0x8200b378` exists in `.rdata`, but a reliable code reference was not found in this pass.
- The music database strings contain `ChartUri`, `LyricUri`, `AudioUri`, `ChartContentFilename`, `AudioContentFilename`, `PreviewContentFilename`, `VideoContentFilename`, `ContentId` and `TitleUpdateVersion`.

Hypothesis:

- The `0x822347xx` / `0x822355xx` region is likely involved in constructing lyric asset names or resource keys.
- This may be near the song/DLC content resolution layer, but the direct call chain into IXB parsing has not yet been proven.

## Cross-reference notes

Ghidra's built-in xrefs were incomplete for many strings, probably because this PowerPC binary often materializes addresses through instruction pairs rather than direct data references. Confirmed xrefs from Ghidra include:

- `0x82061658` version error string from `FUN_8249ff68` near `0x8249ffa0`
- writer token strings such as `<Objects>`, `</Classes>`, `<Classes>` and `NumOfElements` from code around `0x824aab18` to `0x824ab320`
- some unrelated file-image metadata strings from code around `0x82412298`

Additional string references were found by scanning PowerPC instruction pairs:

- FileIO tag/name/version error strings loaded around `0x8249fe84`, `0x8249ff2c` and `0x8249ff98`
- IXB writer tokens loaded around `0x824aaa68` to `0x824ab6f0`
- IXB reader tokens loaded around `0x824ad000` to `0x824ad268`
- `%s_Lyric` loaded around `0x822347b4`, `0x82235414` and `0x82235504`

## Vermutete Dateistrukturen

Confirmed by code:

- There is a serializer format using class/object/member metadata with token names:
  - `Classes`
  - `Class`
  - `Members`
  - `Member`
  - `Objects`
  - `Offset`
  - `Size`
  - `Base`
  - `Name`
  - `Uri`
  - `UriList`
  - `Key`
  - `IsBigEndian`
  - `NumOfElements`
- Writer-side strings show XML-like syntax for at least one representation:
  - `<Classes>`
  - `<Objects>`
  - `<Member ...>`
  - `NumOfElements="%d"`
  - `IsText="false"`
  - `IsBigEndian="%s"`

Hypotheses to verify against sample files:

- IXB likely has a metadata section describing classes, members, object offsets and object records.
- `Offset` and `Size` probably point from metadata records into serialized binary object data.
- `UriList`, `Uri` and `Key` may describe external resource references or embedded URI tables.
- The short strings `NFT`, `DDS` and `ixb` near the reader tokens may be accepted resource type / extension markers, but their exact role is not proven.
- A separate binary header object may contain the validated 4-byte tag, 4-byte name and version fields observed in the FileIO functions.

## Offene Fragen

- Which function opens the outer `.X360` song file and hands its stream/buffer to the IXB serializer reader?
- Does the `.X360` file use the observed FileIO header at offset `+0x10`, or is that only used by nested engine chunks?
- Where is compression handled for X360 content? Strings for `UseCompressToolForX360` exist, but no loader/decompressor path was confirmed yet.
- Are STFS/package APIs dynamically imported, statically linked, or hidden behind Xbox runtime calls not recovered by Ghidra imports?
- Why does Ghidra misidentify some function boundaries around `0x824acff0`, `0x822347xx` and `0x822355xx`? Fixing function prologue/no-return analysis should improve decompilation.
- What are the exact helper roles of `0x824b2cf8`, `0x824b3c50`, `0x824b30e0`, `0x824b1110`, `0x824b2290`, `0x824b1d18` and `0x82ac22b8`?

## Next concrete parser steps

1. Extend the Python analyzer to report the presence and byte offsets of the serializer tokens listed above in every sample `.X360` / IXB file.
2. Add a sample-file probe for the possible FileIO header layout:
   - 4-byte tag
   - 4-byte name
   - 16-bit version
   - optional adjacent 16-bit field
3. Keep the first writer target aligned with the compact Lips 1 format described in `docs/lips1_target_profile.md`, excluding LS2-specific timed gesture/noisemaker/hit-marker layers for now.
4. Build a schema report for each sample that lists:
   - class names
   - member names
   - member offsets
   - object offsets/sizes
   - URI entries
5. Compare compact Lips 1 samples against LS2/extended samples and flag only structural differences that are visible in the parsed metadata, not guessed from filenames.
6. Once object offsets are reliable, implement a minimal writer that preserves the serializer metadata shape but replaces known song-owned content fields.
7. Add tests for malformed tag/name/version checks after confirming which real sample bytes correspond to the FileIO header validators.

