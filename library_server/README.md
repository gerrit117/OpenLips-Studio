# OpenLips Library

[English](README.md) | [Deutsch](README.de.md)

A private home-network song library for Studio, the Xbox client and a WebUI.
This is **not the public community website**.

## Simple Docker setup

The container uses **bridge networking and one HTTP port**. No host IP
configuration, discovery, FTP, TLS, login or pairing is required.

```sh
docker pull ghcr.io/gerrit117/openlips-library:latest
docker compose up -d
```

Run Compose from this directory. Open `http://YOUR-SERVER-IP:8765`.
Enter the same address manually in Studio's Remote Library or the Xbox client.
To change the host port, set `OPENLIPS_WEB_PORT` before starting Compose.
The internal container port remains 8765.

### Unraid

Use [the template](unraid/OpenLips-Library.xml) or add a container:

| Setting | Value |
|---|---|
| Name | OpenLips-Library |
| Repository | ghcr.io/gerrit117/openlips-library:latest |
| Network | Bridge |
| Privileged | No |
| TCP container port | 8765 |
| TCP host port | 8765 |
| Container appdata path | /data |
| Host appdata path | /mnt/user/appdata/openlips-library |
| Container song-library path | /library |
| Host song-library path | /mnt/user/OpenLips-Library |
| Data access | Read/Write |
| PUID variable | 99 |
| PGID variable | 100 |
| WebUI | http://[IP]:8765/ |

Leave Extra Parameters and Post Arguments empty. Remove old OPENLIPS_BIND,
FTP ports and host-network settings. No manual server.json editing is needed.
Use a dedicated appdata directory, not a whole media share.

The startup helper prepares ownership of /library and its contents,
then drops root permanently. The server runs as PUID/PGID, not root.
Existing server.json is left untouched and no longer controls networking.
Projects, media, packages and the database are stored directly in /library,
not appdata. Choose a dedicated Unraid share for this mapping.
To migrate an existing collection, stop the container and copy the **contents**
of /mnt/user/appdata/openlips-library/library into the chosen library share.
Include library.sqlite3 and all subdirectories. Keep the original until the
new collection has been verified. No automatic moves or deletions are performed.

Place the template at
`/boot/config/plugins/dockerMan/templates-user/my-OpenLips-Library.xml`
and select it under Docker > Add Container.

## Updates and backups

Relevant main-branch changes automatically build and test Linux amd64 before
publishing latest. Immutable sha-<full-commit> tags allow rollback.
Pull updates and recreate the container; retain the data volume.
The health check uses localhost inside the container and requires no credentials.

Back up /library and /data while stopped. Do not use `docker compose down -v` unless you
intend to delete the collection. Local build:

```sh
docker compose -f compose.yaml -f compose.build.yaml up -d --build
```

## Features

- English/German WebUI with light/dark themes, catalog search and metadata editing.
- Import UltraStar TXT, vocal MIDI, LRC, .ols and portable .olp.
- Retain covers, audio, video, projects and prepared DLC/song-pack files.
- Convert charts/lyrics and export native Lips data, MIDI or LRC.
- Shared HTTP API for Studio and the Xbox client.

The Songs view includes ready DLCs and every song inside a song pack, even
without an editable project. The Type column distinguishes DLCs, projects,
community imports, UltraStar, MIDI and LRC. Ready DLC details offer the original
package download and its Xbox Content destination. Selecting one song from a
pack downloads the complete pack, not an extracted single-song package.
The Downloads view remains available for all prepared files and export versions.

LRC-only drafts need pitches before scored chart export. Compatible media
encoding still requires Windows and is not enabled in this container.
USDB, public community imports and console-agent transport remain inactive.
Studio's desktop server retains its separate optional discovery/FTP features.

## Network scope

HTTP has no authentication: everyone with network access can manage the library.
Use it only on your trusted home network. Do not forward the port to the Internet.
No analytics or external fonts; only theme/language preferences are stored in
the browser. Uploads are treated as data, never executed as programs.

## Credits

Qt for Python, Mido, Pyphen, Pillow, pyftpdlib, python-zeroconf/ifaddr,
cryptography and Lucide are credited in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).
Share only material for which you have the necessary rights.
OpenLips is independent of Microsoft, Xbox and the creators/publishers of Lips.
