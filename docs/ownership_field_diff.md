# IXB Ownership Field Diff Notes

This note is a focused, read-only comparison of the ownership/container fields
that are most likely to cause the current synthetic lyric IXB hard crash.

Generated local report:

```powershell
py tools\compare_ownership_fields.py `
  --real-lyric private\samples\lyrics\1234_Lyric.X360 `
  --synthetic-root private\outputs\minimal_ixb_variants `
  --stem 1234_Lyric.X360 `
  > private\outputs\minimal_ixb_variants\ownership_field_diff.txt
```

The generated report is intentionally kept under `private/outputs` and should
not be committed.

## Compared Files

Known-working real lyric:

- `private/samples/lyrics/1234_Lyric.X360`
- size: 5158 bytes
- plain IXB
- Objects range: `0x00000AF9-0x00001416`
- Text resources:
  - resource 0: payload `0x00000B2D-0x000011AF`, length `1666`, hash `0x14BB2C10`
  - resource 1: payload `0x000012BE-0x00001312`, length `84`, hash `0x07198CC0`

Synthetic variants compared:

- `bare`
- `tags`
- `lyric-ownership`
- `full-current`

Only `lyric-ownership` and `full-current` include the synthetic ownership
chain. Both show the same high-signal ownership mismatch.

## Strongest Finding

The real `ixRawFileImage` appears to store the Text resource payload hash in the
field currently decoded as `data_ptr`.

Real canonical `ixRawFileImage`:

- tag: `0x54`
- offset: `0x000012BD`
- `asset_package_ptr = 0x0719D6C0`
- `data_ptr = 0x14BB2C10`
- `data_reserve = 1666`
- `data_size = 1666`
- `type_name_ptr = 0x099221E8`
- `type_reserve = 5`
- `type_size = 5`

That `data_ptr` value exactly matches Text resource 0's payload hash:

- Text payload hash: `0x14BB2C10`
- Text payload length: `1666`

Synthetic canonical `ixRawFileImage` in both `lyric-ownership` and
`full-current`:

- tag: `0x54`
- offset: `0x00000C4B`
- `asset_package_ptr = 0x05000400`
- `data_ptr = 0x05000900`
- `data_reserve = 22`
- `data_size = 22`
- `type_name_ptr = 0x05000800`
- `type_reserve = 5`
- `type_size = 5`

The synthetic Text resource hash is `0x12345678`, but the synthetic
`ixRawFileImage.data_ptr` is currently the fake runtime pointer
`0x05000900`.

Conclusion: the synthetic ownership chain likely uses a runtime-style pointer
where the real file layout stores the referenced Text payload hash. This is the
cleanest field-level crash suspect.

## Vector And Container Notes

No high-confidence synthetic ownership candidate currently shows
`count > 0` with a null pointer. Zero/null allocator-like fields also occur in
the real file, so zero allocator fields alone should not be treated as fatal.

Real `ixAssetPackage` canonical asset vector:

- tag: `0x5C`
- offset: `0x00001335`
- `asset_vector_ptr = 0x071989C0`
- `asset_vector_reserve = 32`
- `asset_vector_size = 1`

Synthetic `ixAssetPackage` canonical asset vector:

- `asset_vector_ptr = 0x05000500`
- `asset_vector_reserve = 1`
- `asset_vector_size = 1`

This is not an obvious null/count violation, but it still differs from the
real file's reserve/capacity style.

`ixVector<char>` is more suspicious than the schema names imply. The real file
layout appears to inline string bytes sooner than the synthetic runtime-style
layout:

- real preview at vector body `+8`: starts with visible inline name/text bytes
  such as `234_Lyric...`
- synthetic preview at vector body `+8`: starts with runtime-style size and
  allocator words before text: `00 00 00 14 00 00 00 00 TinySynthetic_Lyric...`

Conclusion: at least some `ixVector<char>` records should probably be emitted
with the real compact/file-layout representation, not the current
runtime-style `_data/_reserve/_size/_allocator` serialization.

## Variant Interpretation

- `bare`: no ownership chain, so no `ixRawFileImage` or `ixAssetPackage`
  mismatch is present.
- `tags`: marker tags and `NumOfElements` only; still no ownership chain.
- `lyric-ownership`: introduces the ownership chain and immediately shows the
  `ixRawFileImage.data_ptr` hash-vs-pointer mismatch.
- `full-current`: same ownership mismatch as `lyric-ownership`.

This lines up with the Xbox behavior change: adding ownership makes the game
traverse these fields, and the malformed `ixRawFileImage` / vector layout is a
stronger crash suspect than marker tags or object count alone.

## Next Safe Direction

Do not add more chart roots or sequence/controller structures yet. The next
implementation step should first make the synthetic ownership serialization
match the real file layout for:

- `ixRawFileImage.data_ptr` / resource hash reference
- `ixVector<char>` string/resource field layout
- `ixAssetPackage` vector reserve/capacity conventions

Then regenerate only the existing controlled variants and retest.
