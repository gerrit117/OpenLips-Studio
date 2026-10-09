# OpenLips Xbox Client

[English](README.md) | [Deutsch](README.de.md)

Native Xbox 360 library client in the OpenLips style. The local development
build uses an existing official SDK; no Microsoft SDK headers, samples or
tools are distributed in this repository.

## Home-Network Workflow

- Automatically discover open libraries via mDNS, or enter a private IPv4 address.
- Connect over HTTP without accounts, passwords, TLS or pairing.
- Browse/search songs, view covers and follow server build-job progress.
- Download prepared DLCs, verify their size/SHA-256 and retain cached copies.
- Optionally copy completed packages to a chosen Xbox Content location.
  Incomplete transfers are staged separately; existing files are not replaced.
- English/German, dark/light themes and a built-in search keyboard.

Media encoding stays on the Windows library helper. The Xbox is not an encoder.
Installed-song inventory reconciliation, a console-side FTP server and direct
USDB/community requests are not yet implemented.

## Build Locally

`tools/build_xbox_client.py` builds the client from our sources, the installed
SDK and pinned open-source dependencies. Generated output belongs in ignored
`private/` folders. Supply a font you are permitted to use; the locally generated
font atlas is not a public redistribution asset.

The separate title ID is `4F4C5043`, not the Lips title ID. Keep `default.xex`
and its accompanying `media/` directory together. The output is unsigned
homebrew for a modified console, not an officially signed retail application.
The SDK development image is preserved separately; the preparation tool only
accepts this client's own title ID and does not modify game executables.

## Verification

The native client rendered its OpenLips interface in Xenia. The host transport
tests cover anonymous HTTP, catalog parsing, verified downloads, offline cache,
Content staging/read-back and no-overwrite behavior.
**Physical Xbox/Aurora startup, controller input, device-to-device discovery,
cover rendering and actual DLC installation still require console testing.**
Successful local compilation or an emulator screenshot is not proof of those.

See [Library setup](../library_server/README.md) and
[the API documentation](../docs/xbox_library_server.md).
Keep this anonymous service on the trusted home network; no Internet port forwarding.
