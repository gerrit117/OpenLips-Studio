# Library Changelog

## Simple HTTP Container

- Replace host networking with standard Docker bridge networking and one published HTTP port.
- Remove FTP and discovery from the container; connect by entering the library address manually.
- Ignore legacy server.json network settings, certificates and credentials without deleting them.
- Prepare dedicated appdata ownership automatically, then run the application as configurable PUID/PGID.
- Preserve existing library projects, media, packages and database contents.
- Use an internal HTTP health check and verify forwarded ports, restrictive mounts and restarts before publication.

## Storage Compatibility Fix

- Stop changing permissions on host-mounted data directories during startup.
- Explain storage permission failures without repeated Python tracebacks.
- Document recovery of existing Unraid appdata ownership without deleting library files.

## Initial Container Release

- Publish the Linux amd64 home-network library on GHCR.
- Build, test and publish updated images automatically after relevant main-branch changes.
- Open the bilingual WebUI without login, TLS or device pairing.
- Import UltraStar, MIDI, LRC and portable Studio songs; export native charts, MIDI and lyrics.
- Retain prepared DLC packages and share them through HTTP or anonymous read-only FTP.
- Advertise libraries using mDNS and preserve the collection across container updates.
- Add an Unraid template with persistent appdata and host networking.
- Keep compatible media encoding on the Windows helper; it is not enabled in Docker.
