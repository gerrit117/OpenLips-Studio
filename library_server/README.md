# OpenLips Library

[English](README.md) | [Deutsch](README.de.md)

A private home-network song library shared by Studio, the Xbox client and a
self-hosted WebUI. This is **not the public community website**.

## Connect

The default is **HTTP without authentication**. No accounts, passwords, access
keys, certificates or device pairing are needed. Anyone on the reachable home
network can use and manage the library.

Studio and the Xbox client discover libraries through mDNS
(`_openlips._tcp.local.`). Studio connects automatically when it finds one open
library; choose a library when several are available. A private IP address can
be entered manually if multicast is blocked by the router, VLAN or VPN.

In Studio, enable the Library workspace and start its local server to share
your collection. Opening Studio alone does not start a server. The library's
FTP service provides prepared files anonymously and read-only. Copying from
Studio to Aurora is a separate connection and still follows Aurora's own FTP
configuration.

## Docker

Run from this directory:

```sh
OPENLIPS_BIND=192.168.1.100 docker compose up -d
```

Replace the example with the Docker host's private IPv4 address. Open
`http://192.168.1.100:8765`: the catalog opens directly, without a login page.

Pull directly: `docker pull ghcr.io/gerrit117/openlips-library:latest`.
Changes on `main` automatically build and test Linux amd64 before publishing
`latest`; immutable `sha-<full-commit>` tags allow rollback. Pull the updated
image and recreate the container to update; the app does not restart its host.

### Unraid

Use [the Unraid template](unraid/OpenLips-Library.xml), or add a container with
repository `ghcr.io/gerrit117/openlips-library:latest`, network **Host**,
`OPENLIPS_BIND` set to Unraid's LAN IPv4, and
`/mnt/user/appdata/openlips-library` mapped read/write to `/data`.
The directory must be writable by UID/GID `10001`:

```sh
mkdir -p /mnt/user/appdata/openlips-library
chown 10001:10001 /mnt/user/appdata/openlips-library
```

If an existing installation reports `Permission denied: /data/server.json`,
stop the container and correct ownership of this dedicated appdata directory,
including files created during earlier attempts:

```sh
chown -R 10001:10001 /mnt/user/appdata/openlips-library
chmod u+rwx /mnt/user/appdata/openlips-library
```

Use your actual mapped directory if different. Do not apply this to the whole
appdata share. Pull the latest image and restart; the application no longer
changes permissions on the host's mount point. Keep the `/data` mapping
read/write. Existing library files remain in place.

Place the template at
`/boot/config/plugins/dockerMan/templates-user/my-OpenLips-Library.xml` and
select it under **Docker > Add Container**. No privileged mode or TLS needed.
Apply new images through Unraid's update action; keep appdata during updates.
Local build: `docker compose -f compose.yaml -f compose.build.yaml up -d --build`.

The data volume persists across upgrades. Host networking lets mDNS discovery
and passive FTP work on Linux. Docker Desktop requires host-network support.
Ports: HTTP TCP `8765`, FTP TCP `2121`, passive FTP TCP `50000–50009`,
mDNS UDP `5353`. Do not forward these ports to the Internet.

The image runs without root privileges or access to the Docker socket.
Only selected Studio/toolset files and local UI assets enter the image;
the private community website, original games, songs and secrets do not.
Back up the complete library volume while the server is stopped.
Do not use `docker compose down -v` unless you want to delete that data.

## Features

- English/German WebUI with light/dark themes and catalog search.
- Import UltraStar TXT, vocal MIDI, LRC, `.ols` and portable `.olp`.
- Retain cover, audio and video; edit song metadata as a new snapshot.
- Assign timed lyrics to notes and export Lips charts/lyrics, MIDI or LRC.
- LRC-only drafts need pitches before they can become scored charts.
- Store and download prepared Studio DLCs and song packs.
- Shared API for local/remote Studio and the native Xbox client.

Portable media transcoding, native console-agent transport, USDB requests and
community-site imports remain inactive in the Docker service. Their prepared
endpoints return `501`. The currently verified media encoding path still
requires Windows; chart/lyric conversion does not.

The service does not execute uploaded files as programs. File-size limits,
path validation, hashes and incomplete-transfer staging remain in place;
these do not require user authentication. Everyone with network access is
trusted to manage the collection. No analytics, external fonts or embeds are
used; only theme/language preferences are stored in the browser.

## Development

```sh
python -m library_server.app --config /absolute/library/server.json --library /absolute/library/data --bind 192.168.1.100
```

Existing configurations switch to open LAN mode on normal startup. Previously
generated certificates remain on disk but are not used. The optional legacy
authenticated mode is available explicitly with `--authenticated`; it is not
required by the home-network workflow.

See [the shared API documentation](../docs/xbox_library_server.md) and
the local Xbox client. Windows API/client tests do not
replace an actual Docker/Linux or physical Xbox test.

## Credits

Qt for Python, Mido, Pyphen, Pillow, pyftpdlib, python-zeroconf/ifaddr,
cryptography and locally bundled Lucide icons are credited in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
Use/share only material for which you have the necessary rights.
OpenLips is independent of Microsoft, Xbox and the creators/publishers of Lips.
