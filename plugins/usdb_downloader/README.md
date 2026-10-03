# USDB Downloader

Independent OpenLips process-plugin bridge to
[USDB Syncer](https://github.com/bohning/usdb_syncer), by Markus Böhning and its
contributors. Studio renders native search/download controls; the isolated plugin
calls upstream functions without opening the Syncer application. Upstream integrates
[yt-dlp](https://github.com/yt-dlp/yt-dlp) and the extended `#VIDEO` metadata
used to retrieve associated audio, video and images.

The Windows x64 `.opl` includes its own runtime, upstream application, FFmpeg,
FFprobe and Deno. No Python or downloader paths need to be configured in Studio.
Offline tests exercise the real upstream window, bundled tools and synthetic
song import. Live authenticated downloads still require user testing; offline
tests are not proof of a working account/download flow. Native macOS/Linux
packages are not yet available.

## Intended workflow

1. Install and explicitly trust the matching platform `.opl` in Studio.
2. Open **Tools > Plugin tools > USDB: Search songs**.
3. Sign in to your USDB account. The password passes through a process pipe,
   is cleared from the input field and is not saved to settings/job files/logs.
4. Search by artist/title. Searches query USDB directly, 100 results per page;
   Studio does not download the entire catalogue first.
5. Select one or multiple songs, confirm your download permission and choose **Download and use**.
   Studio copies chart/media/cover into its persistent import library. Nothing
   replaces the current project until successful import; replacement is undoable.
   The optional direct Song Pack export skips manual editor review, not technical
   validation. The current package backend supports up to 16 songs per pack.

The manual YouTube downloader is built into Studio and works without this plugin:
**Tools > Download YouTube media**. UltraStar imports with a supported `#VIDEO`
reference offer it automatically when project media are missing.

USDB authentication is required for new TXT downloads. Media availability,
provider restrictions and download rights are separate matters. Credentials
remain in memory for the lifetime of the search window;
settings/database/library are isolated from any separately installed Syncer.
Video defaults to at most 720p. Studio performs subsequent Xbox conversion;
the plugin does not claim the downloaded media is already Xbox-compatible.

Closing the integrated download window stops its worker. On Windows, child
FFmpeg/downloader processes are stopped as well. Network actions remain user-controlled.

## Source development / offline test

Create an isolated Python 3.11 environment and install
`tools/usdb_plugin_requirements.txt`. FFmpeg and FFprobe must both be available
to this development runtime. Run:

```text
python plugins/usdb_downloader/worker.py --self-test --output <new-test-folder>
```

This verifies the actual upstream TXT/meta-tag parser and owned-fixture export
without a USDB account or network media download. Integrated invocation uses
`--serve --output ... --state ...` with newline-delimited JSON requests on stdin.
Replies begin with `OPENLIPS_RPC:` and contain progress, result or error. Download
requests require `rights_confirmed=true`. Authenticated live tests still require
a real USDB account; offline tests do not prove live download success.

Pinned upstream revision:
`c8f9157bed4d45fc646e5d4c4450074ef0925aae`.
Upstream USDB Syncer is GPL-3.0-only. Preserve its license, notices and dependency
licenses when packaging; do not bundle copyrighted songs or stored credentials.

## Native packaging

Check out the pinned upstream source, install the requirements in a separate
environment, and run its `src/tools/generate_pyside_files.py` from that checkout.
Set `OPENLIPS_USDB_SOURCE` to the checkout and `OPENLIPS_USDB_MEDIA` to a directory
containing FFmpeg/FFprobe. Inventory dependency licenses into
`build/usdb-licenses`, then build `USDBWorker.spec`. Test the frozen executable
with `--self-test --output <new-folder>` before running:

```text
python -m tools.package_usdb_plugin
```
