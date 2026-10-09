# Working Agreement

- Work, commit and push on `main` unless the user explicitly requests another
  branch. Do not create development branches or worktrees by default.
- Publish downloadable GitHub Releases, not just version tags. Keep changelogs
  in English and user documentation in correct English/German.
- Keep Studio release downloads limited to the Windows setup executable, macOS
  Apple Silicon/Intel DMGs and the Linux installation archive. Do not publish
  duplicate portable archives or standalone checksum files in the main release.
  Distribute optional AI runtimes and external `.opl` plugins separately. Migrate
  automatic download clients before removing runtime assets they still need;
  preserve integrity verification internally. The plugin catalog must not offer
  already-integrated Studio functions as separately installed plugins.
- Bump the app version before publishing changed application/build code from
  another commit. Never move an existing release tag or silently replace a
  released version with different source code.
- Keep original local game files, samples and media. Do not commit copyrighted
  samples, generated song/media outputs, game binaries or decompiled game code.
  Use synthetic committed tests. Private analysis belongs in ignored folders.
- Game-file tests need hash-checked backups and restoration. Do not alter ISOs
  or claim in-game acceptance based only on structural/frozen-build tests.
