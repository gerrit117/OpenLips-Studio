# Studio plugins and Basic Pitch

## Using the built-in plugin

Open **Werkzeuge > Plugins**, or the plug icon in the toolbar. Select Basic Pitch
and explicitly enable it. Choose a local WAV, FLAC, MP3, OGG or M4A recording.
An isolated vocal track gives a more useful draft than a full band recording:
Basic Pitch is instrument-agnostic, not a vocal source-separation model.

Adjust onset/frame thresholds (0..1), minimum note duration (milliseconds),
and minimum/maximum MIDI pitch. The defaults restrict predictions to MIDI 45..84.
Lower thresholds can recover quieter notes but also increase false detections.
The strongest-note option selects the highest-confidence concurrent note and
merges adjacent segments at the same pitch. This is a simple monophonic filter,
not a guarantee that the chosen voice is the singer. Keep-all retains overlaps.

Start analysis. The dialog stays responsive, shows the current analysis stage
and a bounded log, and allows cancellation. The progress bar is indeterminate
during inference: no invented duration estimate or fake percentage is displayed.
Cancellation kills only the isolated worker and never changes the editor project.
The first 200 notes are shown in the result table; the summary counts all notes.

Save the draft MIDI separately, or explicitly take the notes into the editor.
Existing notes and their syllables are replaced after confirmation. Project
title/artist/BPM, cover/video references and lyric draft are preserved. If there
is no existing reference media, the source recording becomes the audio reference.
Undo restores the previous notes and media link. Lyrics, sung syllable boundaries,
phrase/page breaks and musical tempo are **not inferred** by this plugin.
Review/edit the draft before assigning lyrics or exporting a Lips song.

Basic Pitch runs locally. No Spotify account/API key, audio upload or internet
connection is required for analysis after downloading the complete app archive.
The model and ONNX runtime are included separately from the Qt editor. Studio
does not crash or discard work if the worker is missing or fails; see its log.
Optional compressed-codec decoding depends on the bundled SoundFile/libsndfile
support. Convert problematic inputs to PCM WAV before retrying.

## Runtime and native builds

Studio may use Python >=3.11. Basic Pitch 0.4.0 has older backend dependency
constraints, so its worker uses a **separate Python 3.11 ONNX environment**, not
the GUI interpreter. No TensorFlow, CoreML or cloud backend is needed.
Setuptools <81 is required by Resampy's current `pkg_resources` import.

For development, create an isolated Python 3.11 environment, then run:

```sh
python -m pip install -r tools/basic_pitch_requirements.txt
python -m pip install --no-deps basic-pitch==0.4.0
python studio/basic_pitch_worker.py --self-test --output private/worker-source-smoke
python -m PyInstaller --noconfirm BasicPitchWorker.spec
python tools/collect_runtime_notices.py --out dist/OpenLipsBasicPitch/licenses
```

Switch back to the GUI environment before building `OpenLipsStudio.spec`.
The app spec embeds `dist/OpenLipsBasicPitch` into its private runtime directory.
The finished worker is copied intact **after** the GUI's PyInstaller analysis,
preserving executable permissions, native library paths and internal symlinks.
Its Python 3.11 binaries must not be re-analyzed/rewritten as GUI Python 3.12
libraries. macOS app bundles are ad-hoc re-signed after adding the worker; they
are not Apple Developer signed or notarized. CI tests the actual `.app`, too.
The intact macOS worker lives in `Contents/Resources/plugin-runtime`, not in
`Frameworks`: Apple's signing tool interprets mixed metadata directories there
as malformed code bundles. The copied worker retains its original individual
ad-hoc signatures, and the outer app is signed without recursive reclassification.
Intel macOS uses Numba 0.62.x or earlier, which still provides upstream wheels;
newer releases would require an unsupported LLVM source-build path.
Source-mode Studio discovers a built worker automatically, or accepts a Python
path from the plugin dialog for development. Release builds always use their
bundled worker. Each OS must build its own worker and Qt app. CI tests both
source and frozen inference with a self-generated harmonic tone sequence.
Tests never include songs, downloaded audio or third-party lyric/chart samples.

## Plugin contract (API 1)

Plugins use **`.opl`** packages, distinct from **`.olp`** song projects. A package
is a ZIP containing `openlips-plugin.json` and its Python module/resources.
Choose **.opl installieren** in the manager. Installation validates API/path/size
limits and extracts to a new per-user plugin directory; it does not run the
plugin. Activate it separately only if you trust its code. Duplicate installed
IDs are rejected rather than overwritten. Removing the folder link leaves its
local files intact. The first Basic Pitch `.opl` adapter is preinstalled in
`studio/assets/basic-pitch.opl`; its native runtime is bundled separately for
each OS. It does not need to be installed again. Third-party plugins can be
distributed independently as `.opl`.

To package a plugin directory:

```sh
python -m tools.package_studio_plugin examples/plugins/first-importer --out example-importer.opl
```

Packages have a 16 MiB unpacked/256-entry limit and cannot contain traversal
paths, symlinks or duplicate names. Large ML runtimes should use a separate
native worker, not inflate the small plugin code package.

Existing `openlips_studio.importers` entry-point factories remain supported.
They return `studio.plugins.ImportPlugin`; legacy `import_file(Path)` callables
run in a thread and must return a validated `StudioProject`. Legacy threads
cannot be safely killed; the dialog must wait until they finish.

Release users can also link a local plugin folder containing:

```json
{"id": "my-importer", "label": "My importer", "module": "plugin.py", "factory": "create_plugin"}
```

The module must be a Python file within that folder. A single-module example:

```python
from studio.plugins import ImportPlugin
from studio.model import StudioProject, EditorNote

def import_file(path):
    return StudioProject(title=path.stem, notes=[EditorNote(0, 1, 60)])

def create_plugin():
    return ImportPlugin('my-importer', 'My importer', ('.txt',), import_file)
```

Manifests are read without executing plugin code; only explicitly enabled
plugins are loaded. Enablement and parameter values are stored in local Qt
settings. Removing a folder link does not delete any plugin files.
**Plugins execute arbitrary code with your user privileges; this is not a
sandbox or marketplace.** Trust the source before enabling one. Frozen apps
cannot magically provide every third-party Python dependency; prefer an
isolated process runner for plugins with native or conflicting dependencies.

Parameterized importers supply `parameters: tuple[PluginParameter, ...]` and
`create_command(request_path, output_dir, python_override) -> list[str]`.
The host builds float/int/bool/choice controls and starts the command without a
shell. Request JSON is `{protocol: 1, input: absolute_path, options: {...}}`.
The worker writes a `StudioProject.to_payload()` to `output_dir/result.json`
and may write `draft.mid`. Exit nonzero for failure; no result is then accepted.
Optional stdout lines prefixed `OPENLIPS_PLUGIN:` contain a JSON `message`
and optional `progress`. Other stdout/stderr is logged, never interpreted as code.
Results have the same 100,000-note and 64 MiB safety limits as Studio projects.

The current API handles import/draft generation, not arbitrary editor widgets
or export hooks. Broader processing/export lifecycle hooks remain planned.

## Branding

The approved Studio wordmark appears quietly at the right of the editor toolbar.
Windows uses a multi-size ICO in the executable; macOS uses an ICNS in the app
bundle; Linux uses the PNG window icon. An ELF binary does not embed a desktop
launcher icon like a Windows executable. After extracting the Linux build to
its permanent location, optionally install its per-user launcher and icon:

```sh
sh _internal/studio/assets/install-desktop-entry.sh
```

No root access is needed. Move the app later and rerun the script to update the
launcher path. Runtime icons are derived from the approved artwork by
`python -m tools.build_studio_branding`; original artwork is unchanged.

## Credits

Basic Pitch / its model: Copyright 2022 Spotify AB, Apache-2.0, developed by
Spotify's Audio Intelligence Lab and its contributors. See the
[upstream project, authors and research](https://github.com/spotify/basic-pitch).
This plugin is not a Spotify service or an endorsement. Dependency inventories
and shipped notices are included in native archives. See
[third-party notices](../THIRD_PARTY_NOTICES.md).
