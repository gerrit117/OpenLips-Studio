# Xbox Transfer, Library And Local Worker

[English](xbox_library_server.md) | [Deutsch](xbox_library_server.de.md)

These features are opt-in. Studio does not start a network listener, change a
firewall rule or install a background service just because it was opened.

## Copy To Xbox

Use **Tools > Copy to Xbox**, or the same button after exporting a DLC or song
pack. Enter your Xbox's LAN address, Aurora FTP port, username/password and
content root, usually `Hdd1/Content`. Test the connection before copying.

The destination is selected automatically:

```text
Hdd1/Content/0000000000000000/4D530888/00000002/<package filename>
```

Studio validates the complete package, uploads outside the `00000002` directory,
reads the upload back and compares its SHA-256, then renames it into place.
Existing packages are never replaced. Cancellation does not install a partial
DLC. If the connection is lost, an abandoned `.openlips-transfer` staging file
may remain outside the game content directory; it is not an installed DLC.
Packages stay on the PC after copying. The current reader/validator supports
Studio's unsigned, single-copy Lips LIVE packages, not arbitrary Xbox content.

Only non-secret connection preferences are saved. FTP passwords remain in
memory. Standard FTP, including Aurora's usual FTP service, is unencrypted.
Use a trusted LAN or VPN, never port-forward FTP/XBDM or the worker API to the
Internet. Optional FTPS verifies certificates; it does not bypass certificate
errors. Gameplay acceptance still needs testing on your own console.

## Optional Library

Enable **Tools > Enable local library**. The initial local collection uses
the per-user application-data folder; **Choose library folder** selects a
different location without deleting the old one. Switch between local and
remote mode in the Library workspace. The local tab can archive the current
song, import `.olp` projects or prepared Studio DLCs, search, reopen a project,
export selected projects together, and copy a prepared package to the Xbox.

When enabled, successful DLC exports also retain copies of their projects,
audio/video/cover assets and packages. Source files are not moved or deleted.
Identical project content is deduplicated; changed notes, metadata or media
produce another snapshot. Reopening a snapshot starts an editable project,
not an in-place edit of the archived copy. Package metadata is read from the
STFS header and `DLC.xml`, including every song in a pack, not guessed from a
hex filename or display name.

Disabling the library hides the tab but **does not delete its files**. It is
local storage, not a community upload or cloud backup. Allow disk space for
retained source videos and prepared packages. Back up the whole library while
Studio and the worker are stopped. Only `publish/` contains downloadable DLCs;
projects, source media, SQLite state and credentials are outside that directory.

## Headless Worker

Start the library's **Local server** to share it on the home network. Studio
selects a private IPv4 address by default and advertises the library through
mDNS. The normal mode uses **HTTP without authentication**: no API keys,
FTP passwords, certificates or pairing codes. Connection details shows the
addresses, not credentials.

For unattended operation:

```powershell
OpenLipsStudio.exe --server --config "D:\OpenLipsLibrary\server.json"
```

Source equivalent: `python -m studio --server --config PATH`.
Initialize with `python -m studio --server-init --config PATH --library DIRECTORY --bind PRIVATE_IPV4`.
Existing configurations switch to open LAN mode on normal startup.
Local certificate files remain on disk but are unused. The former protected
mode is opt-in via `--authenticated`; the normal home-network workflow does
not need it.

API TCP `8765`, FTP TCP `2121`, passive FTP TCP `50000-50009` and mDNS
UDP `5353` must be reachable between devices. No automatic firewall changes
or Internet port forwarding. Every reachable LAN device may manage the library.
Discovery normally stays within one multicast-capable network; manual private
IP entry remains available. Prepared files are available through anonymous,
read-only FTP and are retained after downloads.

The worker can run under a regular user in Windows Task Scheduler. Windows
service Session 0 encoding has not been verified; no SCM service is installed.

## Client API, Version 1

In the default LAN mode, requests require **no Authorization header** and
`/identity` reports `auth_required: false`. Browsers open the WebUI directly.
The optional legacy authenticated mode retains bearer tokens and device
pairing; its pairing/device routes are not part of the open LAN workflow.
No cookies or URL tokens are used. Browser requests remain same-origin.
Control JSON bodies are limited to 8 KiB; portable imports have separate bounds.

| Endpoint | Result |
| --- | --- |
| `GET /api/v1/identity` | Public server identity and certificate fingerprint; no song catalog or credentials |
| `POST /api/v1/pairing` | Owner enables a five-minute, one-use pairing code |
| `POST /api/v1/pair` | Exchange that code for per-device API and read-only FTP credentials |
| `GET /api/v1/devices`, `DELETE /api/v1/devices/<id>` | Owner lists/revokes paired devices |
| `GET /api/v1/status` | Protocol, encoding capability, FTP port/user and passive ports; no passwords |
| `GET /api/v1/library` | Project, package and chart artifact catalog with IDs, filenames, sizes and hashes |
| `POST /api/v1/import` | Portable TXT/MIDI/LRC/OLS/OLP import: JSON `name`, base64 `data`, optional `title`/`artist` |
| `GET /api/v1/projects/<id>` | Portable project and registered media descriptors, without server paths |
| `POST /api/v1/projects/<id>` | Correct title/artist, returning a new snapshot ID |
| `POST /api/v1/projects/<id>/lyrics` | Assign base64 LRC `data` to existing notes, returning a new snapshot ID |
| `GET/POST /api/v1/projects/<id>/media/<audio\|video\|cover>` | Controlled media download/upload; upload uses raw bytes and `X-File-Name` |
| `POST /api/v1/packages` | Upload a complete Studio DLC for validation and storage |
| `GET /api/v1/packages/<id>`, `GET /api/v1/artifacts/<id>` | Download a registered output; verify the catalog size and SHA-256 |
| `POST /api/v1/jobs` | Queue registered projects; optional `kind`: `dlc` (default), `chart`, `midi`, `lrc` |
| `GET /api/v1/jobs/<id>` | `queued`, `running`, `ready` or `failed`, stage text and result package ID |
| `GET /api/v1/jobs` | Latest 100 jobs |
| `DELETE /api/v1/projects/<id>` | Owner removes a snapshot, without deleting retained media or outputs |
| `POST /api/v1/shutdown` | Stop the worker and its active build process tree |
| `POST /api/v1/transcode`, `POST /api/v1/console-transfer` | Deliberately inactive future backends (`501`) |

Example build request:

```json
{"projects":["registered-project-id"]}
```

For 2-16 projects add `"pack_name":"My song pack"`. The worker only accepts IDs
already registered in its library, **not arbitrary filesystem paths, URLs,
commands or programs**. Builds run serially in isolated subprocesses; there
are at most eight outstanding jobs. Existing matching worker builds are reused
only when projects, ordering, pack name and page-optimization policy match.
Interrupted jobs are marked failed after restarting, not silently resumed.

Chart jobs accept one project, for example
`{"projects":["registered-project-id"],"kind":"chart"}`. The resulting
`.ols` contains native Lips chart/lyrics and cover without audio/video.
`package_id` in the job result also identifies chart/MIDI/LRC artifacts;
look them up in the catalog's `artifacts` collection. These jobs do not require
the Windows video encoder. Unpitched LRC drafts cannot export scored charts.

When ready, look up the result package in `/api/v1/library`, retrieve its
`filename` through FTP and check its byte size/SHA-256 before installing under
the Xbox Content directory. Record console-side installation separately: a
successful PC build or FTP download is not evidence of game recognition.

The [native Xbox client](../xbox_client/README.md) has a local development build;
physical console testing is still required. Console inventory reconciliation
and remote USDB requests/download jobs are not implemented. The Docker WebUI
and anonymous Studio remote access are described in
[OpenLips Library](../library_server/README.md). Existing USDB/media download
controls in Studio remain unchanged. Linux/macOS can serve a prepared
library and convert charts/lyrics; new compatible video encoding still requires
Windows. The Docker deployment intentionally disables new DLC encoding while
retaining prepared packages, imports and chart/lyrics conversion.
