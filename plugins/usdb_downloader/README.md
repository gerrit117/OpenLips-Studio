# USDB Downloader (development)

Independent OpenLips process-plugin bridge to
[USDB Syncer](https://github.com/bohning/usdb_syncer), by Markus Böhning and its
contributors. This plugin opens the actual upstream application rather than
reimplementing its downloader. Upstream already integrates
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and the extended `#VIDEO` metadata
used to retrieve associated audio, video and images.

**Not yet released as a native `.opl`.** The source bridge and Studio's generic
song-import protocol are implemented; native packaging and live authenticated
download validation are still pending. Do not confuse offline fixture tests
with a tested account/download flow.

## Intended workflow

1. Install and explicitly trust the matching platform `.opl` in Studio.
2. Confirm you have permission to download the selected media, then open USDB.
3. Sign in to your USDB account inside Syncer. Never share passwords in chat.
4. Download a song using Syncer's normal search/download controls.
5. Select one downloaded song and use **Tools > Send selected song to OpenLips
   Studio**. Wait for active downloads to finish first.
6. Review the note draft in Studio, then choose **Import song**. Studio copies
   the declared chart/media/cover into its persistent import library. Nothing
   replaces the current project until acceptance; acceptance is undoable.

USDB authentication is required for new TXT downloads. Media availability,
provider restrictions and download rights are separate matters. Credentials
use upstream's OS credential-store integration under a plugin-specific service;
settings/database/library are isolated from any separately installed Syncer.
Video defaults to at most 720p. Studio performs subsequent Xbox conversion;
the plugin does not claim the downloaded media is already Xbox-compatible.

Cancellation is cooperative: Studio asks the window to close, and upstream
stops downloads through its normal cleanup instead of forcibly abandoning
FFmpeg children. Network/browser actions remain user-controlled.

## Source development / offline test

Create an isolated Python 3.11 environment and install
`tools/usdb_plugin_requirements.txt`. FFmpeg and FFprobe must both be available
to this development runtime. Run:

```text
python plugins/usdb_downloader/worker.py --self-test --output <new-test-folder>
```

This verifies the actual upstream TXT/meta-tag parser and owned-fixture export
without a USDB account or network media download. Interactive invocation uses
Studio's API-2 request and `--request ... --output ...`; it additionally needs
`state_dir` and `options.rights_confirmed=true`.

Pinned upstream revision:
`c8f9157bed4d45fc646e5d4c4450074ef0925aae`.
Upstream USDB Syncer is GPL-3.0-only. Preserve its license, notices and dependency
licenses when packaging; do not bundle copyrighted songs or stored credentials.
