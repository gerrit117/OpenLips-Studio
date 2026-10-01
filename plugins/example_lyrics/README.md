# Example lyric mapping plugin

This deliberately small, independent worker illustrates a processing plugin:
read the current chart from the request, assign words from a UTF-8 text file to
chronological notes and return a note draft for explicit review. It does **not**
perform AI recognition, forced alignment or syllabification. Timing, pitch, note
IDs and phrase boundaries remain unchanged.

No external dependencies are needed for source execution. To distribute it,
freeze `worker.py` on each target OS, place the complete resulting folder at
`runtime/LyricMapping/`, and keep the matching entrypoint in the manifest:

```sh
python -m PyInstaller --onedir --name LyricMapping plugins/example_lyrics/worker.py
```

Stage the manifest and `dist/LyricMapping/` in an ignored build directory. Package
that directory with `python -m tools.package_studio_plugin STAGE --out example.opl`.
Install through Studio's plugin manager. See [the full guide](../../docs/studio_plugins.md).
