# OpenLips Song (.ols) v1

`.ols` shares a finished native song chart without its audio/video. It is distinct
from `.olp` editing projects and `.opl` plugins. GUI community transfer is not
released yet; the current source tool prepares a bundle:

```powershell
py -m tools.pack_song_bundle --chart song.X360 --lyric song_Lyric.X360 --cover cover.jpg --title "Original Song" --artist "Original Author" --duration 120 --out song.ols
```

Optional metadata: `--album`, `--genre`, `--language`, `--family og|ls2`. Optional
media reference: `--youtube https://www.youtube.com/watch?v=VIDEO_ID` and `--offset`
in seconds. Exact duration is required without a reference. No downloads occur.
Output must be new: the tool does not overwrite existing files or alter inputs.

## Serialization

Prefix `OpenLipsSong\0\x01\r\n`, then 32 raw SHA-256 bytes of the exact UTF-8
manifest. The remainder is a ZIP with exactly four members:

- `manifest.json`: `format: org.openlips.song`, integer `version: 1`, metadata,
  media reference and each native member's byte size/SHA-256.
- `chart.X360`, `chart_Lyric.X360`: a matching structurally owned plain IXB pair.
- `cover.jpg`: native 256×256 RGB JPEG, up to 512 KiB, no EXIF.

Metadata keys: `title`, `artist`, `album`, `genre`, `language`, `family`.
Media keys: `reference_video`, `duration_seconds`, `offset_seconds`.
Limits: 18 MiB bundle, 8 MiB per IXB, 16 KiB manifest, 17 MiB expanded members,
compression ratio at most 150. Only stored/Deflate members; no passwords, extra
files, directories or symlinks. Native file bytes are preserved without rebuilding.

`tools.song_bundle.decode_bundle` verifies container inventory, hashes, cover and
IXB chart/sequence ownership and lyric WordData coverage. This does **not** prove
in-game compatibility for every layout. Magic and public checksums detect format
or corruption; they are not an authenticity signature and cannot prove Studio
authorship. A malicious author can generate correct hashes.

## Rights

No audio, video, original game data or proprietary templates are included.
Lyrics, musical transcriptions and covers can nevertheless be protected. Share
only material you may legally distribute. A reference URL is not a license to
download or redistribute the linked media.
