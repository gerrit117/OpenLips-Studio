# Experimental OG DLC builder

Song-pack export and verified Xbox Content USB installation are documented in
[Song packs and USB installation](song_packs_usb.md). The current pack-size
limit is now 2016 MiB of assets, with validated level-2 STFS support. This is
a conservative implementation limit, not an asserted Lips format limit.

## Scope and validation

Follow-up: the custom package is enumerated and accessed by Xenia, but the user
reports no song in the OG list. See [DLC import comparison](dlc_import_comparison.md)
for the four-original-package comparison and unresolved native import boundary.

`tools/build_dlc.py` generates a real **unsigned LIVE/STFS marketplace-content
container**, not a renamed directory. Its TitleID is OG Lips `4D530888`, content
type `00000002`. It creates DLC.xml, injects prepared assets, rehashes the
container, independently verifies its header and level 0/1/2 hash trees, extracts
it again and compares every asset's SHA-256. Publication is atomic and refuses
an existing output. Original assets are not changed.

This is for Xenia or a suitably modified Xbox 360. It cannot produce Microsoft's
retail signature and does not make an unsigned package acceptable to an
unmodified console. Hash verification is not signature verification.

The tool supports an existing generated chart/lyric pair or direct UltraStar
input using the fresh OG writer. Studio's Windows DLC export additionally prepares
media automatically and includes the native STFS backend. It does not implement
the LS2 writer, purchase licenses or online leaderboards. The standalone CLI
still accepts prepared assets. Prepared xWMA audio, xWMA preview and
JPEG cover are required; video is optional. MP3 renamed to xWMA is rejected.

Local tests (2026-10-01):

- Synthetic packages: small files, exact 169/170/171 allocated-block boundaries,
  Unicode display titles, extraction roundtrip, deliberate hash corruption.
- Pure synthetic metadata/hash tests, no-overwrite and mocked FTP tests.
- Real private Shape of You package: seven files, 65,767,166 payload bytes,
  16,061 allocated blocks, validated hash tree and byte-identical extraction.
- Second private package generated directly from UltraStar: 780 notes, 384 BPM,
  GAP 15,940 ms; same container validation succeeded.
- **Not yet tested:** in-game DLC discovery/playback on an existing profile,
  real Xbox installation or FTP server transfer. Disc-slot playback of the
  accepted chart/media is confirmed, but is not proof of DLC acceptance.

No existing runtime installation, MusicDB, profile or accepted checkpoint was
changed for these tests. No copyrighted assets or generated packages are
committed.

### Automatic Studio media preparation (0.3.1)

Studio uses the selected video as the audio source, or the selected audio file
when no video exists. Windows Media Foundation encodes WMA Standard (0x0161),
48 kHz stereo, 16-bit, 192 kbit/s. FFmpeg copies the compressed packets into a
WAVE intermediary; Studio writes compact RIFF/XWMA with fmt/dpds/data chunks.
The dpds table is generated from decoded packet sample counts, not guessed from
bitrate. Both containers must decode to identical SHA-256 PCM hashes before
the xWMA is accepted. Full audio and a 15-second preview starting at the first
actual lyric entry are produced separately (shorter if the media ends sooner).
The 15-second default follows 51 of 54 preview paths inspected locally (paths
may include duplicate songs); two were approximately 10 seconds and one 15.2.

Video conversion retains the verified WVC1/WMA Pro path.
Video songs additionally have a separate 240x136 WVC1/WMA Pro preview, cut
from the same first-lyric timestamp and linked with `PreviewVideoUri` in the
MusicVideo entry. Full video encoding is unchanged. See the corpus evidence
and remaining NFT-thumbnail question in [the pack/USB guide](song_packs_usb.md).
Generated charts, lyrics, media, cover and DLC.xml are packaged and independently verified.
Only the destination is chosen in the export dialog. Original media is untouched.
Automatic native encoding currently requires Windows; this is not a claim of
macOS/Linux encoding support or confirmed in-game DLC discovery.

Synthetic audio-only and audio/video tests exercise the full export, extraction,
preview duration, source preservation and no-overwrite behavior. The game still
needs to be tested separately with a real song.

## Native backend

The thin adapter `tools/dlc_backend` uses the existing STFS writer from
[Velocity](https://github.com/hetelek/Velocity) rather than inventing a new
container serializer. The adapter is GPL-3.0-or-later; Velocity is GPLv3 and
its license obligations apply when distributing a linked backend. No external
source checkout or compiled binary is committed here.

Tested dependency revisions:

- Velocity: `cf0b84cc8bbfad09c655476c6a3c762836ce1246`.
- Botan 3.9.0: `07e1cfe0a06b224bbb37ad534736924931184246`.
- MSVC x64, CMake, Python; Botan static library with sha1/rsa/auto_rng modules.

Build Botan from a VS x64 developer prompt in its external checkout:

```powershell
py configure.py --cc=msvc --cpu=x86_64 --os=windows --build-targets=static --minimized-build --enable-modules=sha1,rsa,auto_rng --disable-shared-library
nmake
```

Then build the adapter from the OpenLips root, also in that developer prompt:

```powershell
git -C C:/external/Velocity apply C:/OpenLips/tools/dlc_backend/velocity-full-table.patch
cmake -S tools/dlc_backend -B private/runtime/dlc-backend-build -DVELOCITY_ROOT=C:/external/Velocity -DBOTAN_ROOT=C:/external/botan
cmake --build private/runtime/dlc-backend-build --config Release
```

The small GPLv3 patch corrects an exact-170-block remainder: a full final hash
table must have 170 entries, not zero. Without it some video packages fail
independent hash verification. The release workflow applies the patch to the
pinned dependency before compiling.

Use `--backend PATH` or `OPENLIPS_STFS_BACKEND` to select another executable.
Default: `private/runtime/dlc-backend-build/Release/openlips_stfs.exe`.
Backend entrypoints are `build DIRECTORY OUTPUT TITLE_ID DISPLAY_NAME` and
`extract PACKAGE NEW_DIRECTORY`. Prefer the Python frontend for validation and
rollback-safe publication; the low-level adapter alone does not do those checks.

Initial limits: flat ASCII asset filenames of 1-40 bytes, ASCII output paths,
2016 MiB assets and single-copy STFS hash trees including level 2.
Unicode display titles are supported. Larger packages, nested assets and
dual-copy hash trees are deliberately refused rather than silently
claimed to be supported.

## Build commands

For an already validated chart, package its bytes unchanged:

```powershell
py tools/build_dlc.py --chart private/song/NewSong.X360 --lyric private/song/NewSong_Lyric.X360 --audio private/song/NewSong.xWMA --preview-audio private/song/NewSong_prv.xWMA --jacket private/song/NewSong.jpg --video private/song/NewSong.wmv --title "New Song" --artist "Artist" --uint-id 0x0CCF9001 --duration 263.268 --out private/outputs/NewSong.LIVE
```

Or generate the chart and lyric pair directly from UltraStar, without a template:

```powershell
py tools/build_dlc.py --ultrastar private/song/song.txt --name NewSong --audio private/song/NewSong.xWMA --preview-audio private/song/NewSong_prv.xWMA --jacket private/song/NewSong.jpg --video private/song/NewSong.wmv --title "New Song" --artist "Artist" --uint-id 0x0CCF9002 --duration 263.268 --out private/outputs/NewSong-fresh.LIVE
```

Use unique UintIDs not already installed. There is no console inventory query
yet, so global identity uniqueness remains the caller's responsibility.
The generated manifest uses package-local basenames and consistent content IDs.
Six real MusicIndex entries from four private original DLC manifests informed
the field set; two of four manifests have a MusicVideos group. Preview-video
and NFT preview-icon fields are not generated. Their runtime necessity is
unverified. The minimal metadata uses Pop/EN/2026 defaults, not inferred genre,
language or release year.

The `--chart` path intentionally does not rewrite embedded media URIs. The
direct UltraStar path supplies media stems to the existing OG writer. Whether
the game's DLC music index overrides/binds those names still requires runtime
validation; no guessed new graph structures were added to the accepted writer.

## FTP installation

Default calculated path:

```text
Hdd1/Content/0000000000000000/4D530888/00000002/NewSong.LIVE
```

An existing package can be checked without connecting:

```powershell
py tools/upload_dlc.py private/outputs/NewSong.LIVE
```

Explicit transfer:

```powershell
py tools/upload_dlc.py private/outputs/NewSong.LIVE --host 192.168.1.50 --user xbox --upload
```

Password is prompted, or read from `OPENLIPS_FTP_PASSWORD`; it is not a command
argument or project setting. `--root` handles servers exposing `/Content`
instead of `Hdd1/Content`. `--tls` enables FTPS if supported. Plain FTP sends
credentials and files unencrypted: use only a trusted LAN.

The combined builder also accepts `--ftp-host`, `--ftp-user`, `--ftp-root`,
`--ftp-tls`, and explicit `--upload`. Without `--upload`, it only prints the
destination; it never connects. Upload uses a unique temporary filename,
full read-back SHA-256 validation, then rename. Existing names are refused and
failed uploads clean up only their own temporary file. Standard FTP cannot
provide an atomic no-replace rename against another concurrent uploader;
avoid concurrent installation to the same target.

Do not assume this removes the profile-cache issue until tested. The next
controlled test is DLC enumeration on an existing offline profile, followed
by media/preview binding and a complete song run. Keep the accepted disc-based
song intact as the reference and install only one candidate ID at a time.

## Tests

### Marketplace filenames (2026-10-02)

Studio asks for an output directory and publishes the verified package as
`<40 uppercase hexadecimal header-content-ID characters>4D`, without an
extension. Naming happens after the backend's final rehash and extraction
roundtrip, before atomic no-overwrite publication. The CLI retains explicit
output filenames for diagnostic use. FTP uses the actual emitted filename.

Local corpus: all eight 42-hex-name files found recursively under
`Desktop/Lips/Songdateien` were inspected without modification. These are eight
physical copies representing six distinct names, not eight independent releases.
All have LIVE magic, marketplace content type, Lips title ID `4D530888`, and
suffix `4D` (8/8 copies, 6/6 distinct names). High confidence for this local
Lips convention; not a universal rule for other games.

| File name | Relative folder | Name prefix equals current header ID |
| --- | --- | --- |
| `00C11F2EEFCB355A460A076EF8F4A9B1D084C8774D` | root | no |
| `083E1E9201657F0063535FCA52D0B917CD82A2B24D` | root | no |
| `283B3ADD37FE4DE0189E72144B93E04197A8AA684D` | root | no |
| `00031550837D8EEFEAC978CAEE3B97F3F217154F4D` | DLCs | no |
| `00C11F2EEFCB355A460A076EF8F4A9B1D084C8774D` | DLCs | yes |
| `01865DC82B361FC4C3305CB98B80B45B5E569BBA4D` | DLCs | yes |
| `02E5D2FACD95401040150713774FA36330787D404D` | DLCs | yes |
| `283B3ADD37FE4DE0189E72144B93E04197A8AA684D` | X360 | no |

The name prefix matches the field at `0x32C..0x33F` in 3/8 copies, not a hash
of the whole file, RSA signature or song UintID. Free60 identifies that field
as Content ID / Header SHA1. Two same-name copy groups have identical signature
bytes but different current header IDs, consistent with post-download header
editing and rehashing without renaming. The exact modification history of
the other mismatches is unknown. Medium confidence that the observed naming
was originally derived from the header ID; do not treat mismatches as evidence
of corruption or reject real packages on that basis.

The semantic meaning of the final `4D` has **not** been established. It is a
literal corpus convention here, not an inferred title-ID byte or song-ID field.
Xenia Canary enumerates package files and uses their existing filename when
resolving content paths; it does not require this specific hash-derived name.
Consequently, a diagnostic `.LIVE` filename by itself is not evidence of a
package-discovery or playback failure. Source:
[Canary content manager](https://github.com/xenia-canary/xenia-canary/blob/canary_experimental/src/xenia/kernel/xam/content_manager.cc).

```powershell
$env:OPENLIPS_STFS_BACKEND = "C:\path\openlips_stfs.exe"
py -m pytest -q
```

Without the environment variable, the native integration test is skipped;
pure synthetic hash, XML, publication and FTP tests still run. Format references:
[Free60 STFS](https://github.com/Free60Project/wiki/blob/master/docs/System-Software/Formats/STFS.md)
and the independently implemented reader in
[Xenia Canary](https://github.com/xenia-canary/xenia-canary/tree/canary_experimental/src/xenia/vfs/devices/xcontent_devices).
