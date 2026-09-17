# Runtime Test 4 Summary

## Scope

- Candidate ID: `928d9a4a1e68`
- Role: Lyric
- Corpus family: Lips-1/lps DE level, non-ANZ, non-LS2
- Edit type: one same-length `4 -> 4` ASCII payload edit
- Original game files were not modified.
- Detailed song title, lyric text, and filesystem paths are intentionally kept only in the private test instructions.

## Analyzer Result

The private patched copy was compared against the original with the existing analyzer workflow.

- File size unchanged
- Only the expected four payload bytes changed
- Header unchanged
- Classes unchanged
- `NumOfElements` unchanged
- Marker counts unchanged
- Text-resource coverage remains `100%`
- Payload lengths unchanged
- Pointer-like reference counts unchanged
- Payload-length reference counts unchanged
- Hash-like fields unchanged
- Analyzer diff is empty

## Runtime Question

This test checks whether a minimal same-length edit in the selected lyric payload is loaded by the game at runtime when the path-preserving patched copy replaces the matching lyric file on the console.

## Console Observation

The first attempted resource path did not show the edit. After the matching copy
used by the active game version was replaced, the song loaded and the edited
four-byte lyric text was visibly rendered.

This confirms the payload edit for the tested template. It also demonstrates
that duplicate resources and game-version-specific load paths can make a valid
patch appear ineffective when the wrong copy is deployed.
