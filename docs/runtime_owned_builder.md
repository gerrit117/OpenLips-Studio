# Runtime-owned builder investigation

Work in progress, 2026-09-29. A fully generated OG chart/lyric pair loads and
renders custom note bars and words in Amazing's existing catalog slot. Chart
time does not advance with the media, so playable synchronization is not yet
verified. No new catalog entry or media conversion is complete.

## Isolated test environment

The extracted original Lips 2008 installation was copied into an ignored
private runtime directory. All candidate replacements are confined to that
copy. The source disc image, original extracted installation, and repository
samples are unchanged. A separate configuration and executable are used.

The copied game booted through its intro/title screen. Automated short key
presses were unreliable with the original keyboard driver. A local Canary
patch adds the opt-in `keyboard_minimum_press_ms` setting; the default is zero.
The test uses 150 ms. This build successfully accepted automated Start presses,
skipped the intro and reached the local profile selector. After the user selected
the local profile, ABC playback with untouched chart/lyrics was verified through
visible note bars and readable lyrics. Subsequent song selection is automated.

The patch is saved in `tools/xenia/keyboard_minimum_press.patch`. It is against
the existing local Canary checkout based on aee0871, not a claim of upstream
compatibility. Existing unrelated emulator research edits are preserved.
The patch also protects keyboard binding reads with the existing mutex.
The keyboard-driver library and emulator executable compiled successfully.

For this build Start is X, A is Enter, analog left/right are lowercase A/D,
and digital left/right are Shift+A/Shift+D. Binding Start and A to the same
key does not work reliably: OnKey stops after the first matching binding.

## Corpus findings for the next controlled test

All 119 repository samples were considered; two compressed files remain
unsupported. Counts below use 59 plain lyrics and 58 plain charts. Confidence
is high for occurrence and field layout within this corpus, not for proving
which structures are mandatory to the runtime.

| Lyric ownership observation | Occurrence |
|---|---:|
| Exactly one ixRawFileImage instance | 59/59 |
| Exactly one ixAssetPackage and one ixPackage | 59/59 |
| Exactly three ixDblCnt package-list nodes | 59/59 |
| Separate ixAsset or ixFileImage base instances | 0/59 |
| RawFileImage serialized size 84 | 59/59 |
| Package / AssetPackage sizes 52 / 72 | 42/59 |
| Package / AssetPackage sizes 72 / 92 | 17/59 |

The root package owns one Text asset package through a circular doubly linked
list: a root sentinel, a child node with a package reference, and the child's
self-linked empty-list sentinel. The child asset package owns the most-derived
image through its asset vector. The image back-reference points to that child
package. Base classes are present in schemas but not separate live instances.

`tools/build_lyric_resource.py` creates this ownership candidate from scratch,
with OG and later package-layout profiles, unique record keys, named package
and image, framed raw buffers, and list/reference validation. Existing builder
levels are not changed. The helper accepts opaque payload bytes: real lyric
resource capacity can include non-UTF-8 bytes beyond used text, so UTF-8 decoding
the entire capacity is not a valid structural precondition. Fresh generated
lyrics should still be serialized deliberately rather than copying padding.

## Controlled runtime results

The lyric-only candidates retain the complete original visible resource selected
by chart WordData coverage. The chart, audio, catalog entry, and game executable
remain unchanged. Only the isolated test copy's lyric file is replaced.

| Candidate | Records / bytes | Observed result |
|---|---:|---|
| Original chart and lyric | original | ABC gameplay, readable notes/lyrics |
| Fresh container, shared equal name buffers | 10 / 7207 | Frozen song loading; guest exception |
| Fresh container, independently owned name buffers | 12 / 7246 | ABC gameplay, readable notes/lyrics |

The failed candidate's debugger stack first enters guest code at `0x822AC3B8`,
inside allocator routine `0x822AC2E8`, rather than the previous copy-helper crash.
The name vectors shared two buffers between four owners. Across 59/59 plain
lyric files, all four non-null name/type buffers are distinct (236 fields,
zero within-file aliases). The corrected writer gives every character vector
its own buffer, even for identical strings. A regression test rejects aliases.

The user reported successful loading; an independent automated restart also
reached ABC gameplay with readable opening syllables and note bars. The deployed
corrected file SHA-256 is
`9078e2b1cb0a1c9ab37723f2ff1e7d8a312185225dbf6c4afc986f518524c0e7`.
The observed difference strongly supports an owning-buffer aliasing bug.
Double-free is a plausible mechanism, not yet a traced allocator proof. Confidence
is high for the corpus invariant and this runtime outcome, medium for causation,
and low for generalizing runtime acceptance to other songs or later games.

The corrected lyric ownership graph was also accepted in the Amazing slot with
its original chart. This is a second runtime validation of the lyric container,
not of a custom chart's timing.

## Chart observations

| Instantiated class | Files | Instances |
|---|---:|---:|
| lpsChart | 58/58 | 58 |
| lpsPhraseMarker | 57/58 | 37,757 |
| lpsHitMarker | 18/58 | 3,044 |
| lpsMelodyMarker itself, not derived classes | 0/58 | 0 |
| lpsMusicInfo / lpsMusicIndex | 0/58 | 0 |
| Separate ixAsset / ixFileImage bases | 0/58 | 0 |

All 58 roots contain named Time, Conductor, Audio, Lyric, Melody, Group,
Section, CallAndResponse, Movie, AudioEffect and Led sequences. Duet sequence
names occur in 31/58, so they are not universal. Every Conductor is an
ixTempoMap; every Led root sequence is an lpsLedMasterSequence. Sequence state
names are empty; their asset names distinguish the tracks.

The old synthetic root is unnamed and not owned by its asset vector. It also
creates base MelodyMarker objects, unlike the corpus. These are concrete graph
differences. Whether base marker construction itself fails is still a
hypothesis requiring a loader/runtime test; do not present it as proven.

## ABC source comparison

The ABC chart, lyric, full audio, and preview audio in the re-extracted OG
backup, the older extracted directory, and the isolated game copy were
SHA-256-identical. The original ABC has no full `.wmv`; Amazing has one. The
previously observed ABC behavior (audio proceeds while notes/lyrics wait until
the end) is not explained by accidental edits to those files. It is not yet
proven whether video absence, Xenia timing, or another chart/catalog property
causes it.

## Fresh Amazing chart runtime tests

The test used a four-note SongChart at 4.55-6.55 seconds, text `New Lips test
song`, a fresh chart and fresh lyric IXB, and Amazing's original catalog,
audio and video in the isolated game copy. The chart has one owned root, 11
named tracks, four phrase markers, four linked lyric markers, one audio marker,
one movie marker, and no copied template heap. The generated pair loaded and
displayed the exact four custom note bars and words over Amazing's video.

| Variant | Controlled chart change | Runtime result |
|---|---|---|
| v2 | Movie and audio timing aligned to Amazing | Loads, renders, chart stays still |
| v3 | OG first-word class tokens on chart/sequence/code objects | Same |
| v4 | One Conductor section-pattern code | Same |
| v5 | First tempo time equals Amazing MusicStartOffset, BPM 118 | Same |

Screenshots separated by 10-16 seconds show identical bar positions and lyric
state while the video advances. A fleeting white syllable immediately after
loading is not proof of note progress. Original Amazing reportedly advances
normally; the fresh chart's clock/sequence activation remains the blocker.

In 58/58 readable chart samples, the Conductor has at least one
`ixSeqSongSectionPatternCode`. The current builder now emits one, matching its
observed size (32), OG first-word token, and first type/group/pattern values.
That was necessary for corpus fidelity but did not fix the runtime clock.
All 58/58 lpsChart roots have a nonzero 16-byte `ixAsset.m_aHash` field; the
fresh chart currently zeros it. Its derivation and semantic role remain open.
The chart's sequence vectors and asset fields also use zero allocators where
many real OG files use `0xcdcdcdcd`; whether that matters at runtime is unknown.

The test copy was restored to the re-extracted original Amazing chart and lyric
after testing. Original ISO, extraction and sample directories were untouched.

## Media findings

PyAV/FFmpeg probed the originals and supplied Shape of You files:

| Media | Container / codecs | Duration / size |
|---|---|---|
| OG Amazing `.wma` | ASF, WMA Pro 48 kHz stereo, 192 kb/s | 190.816 s |
| OG Amazing `.wmv` | ASF, VC-1 768x432 at 24000/1001, WMA Pro 48 kHz stereo | 191.146 s |
| Shape MP4 | H.264 1280x720 at 24000/1001, AAC 44.1 kHz | 263.268 s |
| Shape MP3 | MP3 44.1 kHz, stream reports about 183 kb/s | 263.268 s |

The local PyAV build can encode WMV2/WMA2 but not VC-1/WMA Pro. Thus an exact
Amazing-compatible re-encode is not available with the installed codecs.
Whether the game accepts WMV2/WMA2 requires an isolated media substitution
test. The OG evidence does not support assuming that XMV/XMA is mandatory for
this song's full video/audio resources.

## Next discrimination

Compare runtime effects of a nonzero root `m_aHash` and real sequence/vector
file-layout sentinels, one field family at a time. If neither activates the
clock, instrument the OG loader/sequence scheduler in Xenia and compare the
first update against a running original Amazing chart. Only after time advances
should the 770-note Shape of You import and media/catalog registration be used
for an end-to-end song test.
