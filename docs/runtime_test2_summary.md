# Runtime Test 2 Summary

## Scope

- Candidate ID: `6d572f4484b3`
- Role: Lyric
- Family: Lips-1 plain IXB
- Edit type: position-stable replacement of the selected visible ASCII text
  payload
- Original game files and the matching chart were not modified.
- Song title, lyric content, source path, offsets, and deployment path remain
  only in the private test report.

## Replacement Strategy

The selected resource has stable 100% chart-worddata coverage. Its structural
prefix and BOM, whitespace, line breaks, punctuation, decoded character
positions, payload capacity, and existing trailing null padding are preserved.
Post-BOM ASCII alphanumeric runs are replaced by same-length synthetic test
patterns.

This is a full visible-text test without changing chart `LyricWordData` offsets
or lengths. The payload-length field, hash-like field, and pointer fields remain
byte-identical.

## Analyzer Result

- Header and classes unchanged
- `NumOfElements` unchanged
- Marker counts unchanged
- Text resource still selected by chart-worddata coverage
- Coverage remains 100%
- Payload length and file size unchanged
- Existing padding preserved byte-for-byte
- Pointer-like and payload-length reference inventories unchanged
- IXB section bounds unchanged
- All changed bytes are confined to the selected visible payload
- Analyzer snapshot diff is empty

## Runtime Question

The test checks whether the console also accepts a large number of same-length
text-byte changes when the complete template structure, chart mapping, resource
length, padding, and hash-like field are preserved.

## Console Status

The first prepared candidate produced a song-specific media-read error: the
game itself did not crash, but the song had no cover or preview audio and could
not be started. Other original files were still present, so that attempt is
inconclusive for the IXB payload hypothesis.

The second Test 2 attempt used a different Lips-1 plain-IXB song. It had 100%
worddata coverage and passed the complete local before/after validation. The
console loaded the song and correctly displayed the complete synthetic visible
lyric replacement.

This confirms full visible lyric-payload replacement for the tested fixed-layout
Lips-1 template. Payload length, hash-like field, pointer fields, chart mapping,
file size, and object structure remained unchanged. No title, lyric content, or
private source path is included in this document.

Private artifacts and console instructions are under
`private/outputs/runtime_console_test/test2/`.
