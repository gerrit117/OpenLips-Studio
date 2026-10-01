# Experimental OG DLC builder

## Scope and validation

Follow-up: the custom package is enumerated and accessed by Xenia, but the user
reports no song in the OG list. See [DLC import comparison](dlc_import_comparison.md)
for the four-original-package comparison and unresolved native import boundary.

`tools/build_dlc.py` generates a real **unsigned LIVE/STFS marketplace-content
container**, not a renamed directory. Its TitleID is OG Lips `4D530888`, content
type `00000002`. It creates DLC.xml, injects prepared assets, rehashes the
container, independently verifies its header and level 0/1 hash trees, extracts
it again and compares every asset's SHA-256. Publication is atomic and refuses
an existing output. Original assets are not changed.

This is for Xenia or a suitably modified Xbox 360. It cannot produce Microsoft's
retail signature and does not make an unsigned package acceptable to an
unmodified console. Hash verification is not signature verification.

The tool supports an existing generated chart/lyric pair or direct UltraStar
input using the fresh OG writer. It does not implement the LS2 writer, GUI,
automatic media transcoding, purchase licenses or online leaderboards. These
functions are separate from packaging. Prepared xWMA audio, xWMA preview and
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
committed. The xWMA encoder used privately is not distributed.

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
cmake -S tools/dlc_backend -B private/runtime/dlc-backend-build -DVELOCITY_ROOT=C:/external/Velocity -DBOTAN_ROOT=C:/external/botan
cmake --build private/runtime/dlc-backend-build --config Release
```

Use `--backend PATH` or `OPENLIPS_STFS_BACKEND` to select another executable.
Default: `private/runtime/dlc-backend-build/Release/openlips_stfs.exe`.
Backend entrypoints are `build DIRECTORY OUTPUT TITLE_ID DISPLAY_NAME` and
`extract PACKAGE NEW_DIRECTORY`. Prefer the Python frontend for validation and
rollback-safe publication; the low-level adapter alone does not do those checks.

Initial limits: flat ASCII asset filenames of 1-40 bytes, ASCII output paths,
110 MiB assets, single-copy STFS hash trees up to 28,900 allocated blocks.
Unicode display titles are supported. Larger packages, nested assets and
dual-copy/level-2 hash trees are deliberately refused rather than silently
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

```powershell
$env:OPENLIPS_STFS_BACKEND = "C:\path\openlips_stfs.exe"
py -m pytest -q
```

Without the environment variable, the native integration test is skipped;
pure synthetic hash, XML, publication and FTP tests still run. Format references:
[Free60 STFS](https://github.com/Free60Project/wiki/blob/master/docs/System-Software/Formats/STFS.md)
and the independently implemented reader in
[Xenia Canary](https://github.com/xenia-canary/xenia-canary/tree/canary_experimental/src/xenia/vfs/devices/xcontent_devices).
