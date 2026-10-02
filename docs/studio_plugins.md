# Plugin developer guide

## Release policy

New official plugins must be distributed as finished, installable `.opl`
packages through GitHub Releases, not merely as source folders. Source code
remains available for contributors. Publish separate packages for supported
operating systems and architectures, including the worker, required runtimes,
models and redistributable dependencies. Document external accounts or services;
never bundle credentials.

Before release, test installation and execution from the packaged artifact in
Studio, verify cancellation and result import, and include checksums, licenses,
credits and English release notes. Clearly label unsupported platforms and
development-only plugins. A working source bridge is not a completed plugin
release. USDB Downloader packaging follows the current media compatibility tests.

Development extension (not yet a released native USDB package): process plugins
can additionally declare `result_type: "song-import"`, `input_required: false`
and `interactive: true`. Such workers return `result.json` with
`format: "openlips-plugin-song"`, `schema_version: 1`, mandatory relative
`chart` TXT path and optional relative `audio`, `video`, `cover` paths inside
the job folder. Studio validates the declared files and copies them into its
persistent import library only after explicit acceptance. Declared chart plus
assets are limited to 8 GiB; TXT to 16 MiB; the descriptor to 64 KiB. Existing
`note-draft` plugins are unchanged.

Requests also include a per-plugin `state_dir` for persistent settings and
`project` as before. Interactive workers must poll `cancel.request` in the job
directory and shut down their own child processes before exiting. Studio keeps
the job alive until worker cleanup finishes. The host language menu controls
Studio's own labels, not arbitrary upstream/plugin windows. See the
[USDB bridge guide](../plugins/usdb_downloader/README.md) and
[development checkpoint](studio_next_development.md) for remaining release work.

Studio 0.2.1 supports independent **API-2 process plugins**. A plugin ships its own
executable, libraries and optional models in a platform-specific **`.opl`** ZIP.
It can be written in Python, Rust, C++, or another language: Studio communicates
through files and stdout rather than importing the plugin's runtime. **`.olp`**
is the song-project format and must not be used for plugins.

## Installation and trust

Download the `.opl` for your OS and architecture. Open **Werkzeuge > Plugins**,
choose **.opl installieren**, then explicitly enable the installed plugin. Review
its description, author and declared permissions. Installation alone executes no
code. Analysis runs separately; errors/cancellation leave the editor unchanged.
Preview the result before accepting it. Note replacement is undoable.

Studio itself does not include Basic Pitch. The separate Basic Pitch package
contains its model and full ONNX/Python runtime. See the [plugin catalog](../plugins/README.md)
and [Basic Pitch guide](../plugins/basic_pitch/README.md).

**Process isolation is not a security sandbox.** Enabled plugins have your user
permissions and can access files or the network. Permission declarations are
informational, not OS-enforced capabilities. Only install trusted packages.
An LLM/cloud plugin must clearly disclose uploads and service requirements. This
release does not implement an LLM provider, secret vault, download manager or
automatic dependency installer. Never store API tokens in manifests or packages.

Installed packages live under Qt's per-user AppDataLocation `plugins/` directory,
in an `id-version` subfolder. Installation validates first, extracts to a fresh
staging directory and renames only on success. Source archives are untouched.
Removing a manager link disables that plugin but keeps its installed files.
To switch versions, unlink the old version and install/link the new one. Existing
installation directories are never silently overwritten.

## Manifest

At the archive root place `openlips-plugin.json`:

```json
{
  "id": "example-lyric-mapping",
  "label": "Example lyric mapping",
  "version": "1.0.0",
  "api_version": 2,
  "type": "process",
  "protocol": 1,
  "result_type": "note-draft",
  "author": "Your name",
  "description": "Assign words from a text file to existing notes.",
  "extensions": [".txt"],
  "permissions": ["read-selected-text", "read-project", "write-job-output"],
  "entrypoints": {"windows-x64": "runtime/LyricMapping/LyricMapping.exe"},
  "parameters": [
    {"key": "overwrite", "label": "Replace existing fragments", "kind": "bool", "default": false}
  ]
}
```

Supported targets: `windows-x64`, `windows-arm64`, `macos-x64`, `macos-arm64`,
`linux-x64`, `linux-arm64`. Declaring a target does not prove it works: build and
test natively on every claimed target. Basic Pitch currently publishes only
Windows x64, both macOS architectures and Linux x64.

The executable must exist inside the package. Use relative POSIX paths, no shell
command strings, absolute paths or `..` components. Platform compatibility is
checked before installation and again before execution. API version 2 requires
Studio 0.2.1 or later; unknown APIs/protocols/result types are rejected.

Parameters generate standard controls in Studio: `int`, `float`, `bool`, `choice`,
`text`. Numeric parameters require `minimum`, `maximum`, `default`; choices require
`choices: [["Label", "value"]]`. `text` produces a short text input, not a secret
field; values persist in user settings. Labels and descriptive fields are plain
text, not HTML. Use a selected UTF-8 text file for long lyrics. Up to 64 controls
are supported. Validate all options again inside the worker.

## Request and execution

Studio creates a temporary job directory and invokes an argument list directly:

```text
PLUGIN_EXECUTABLE --request /job/request.json --output /job
```

No shell expansion or activation script is involved. Locate private libraries
and models relative to your executable, not the working directory. Plugins must
not depend on Studio's Python interpreter or packages. A separately frozen Python
runtime is supported; Studio resets inherited PyInstaller/library environment
variables for the worker.

`request.json` (UTF-8, at most 64 MiB):

```json
{
  "protocol": 1,
  "input": "/absolute/path/selected-file.txt",
  "options": {"overwrite": false},
  "project": {
    "format": "openlips-studio-project",
    "schema_version": 1,
    "title": "Example",
    "notes": [
      {"id": "note-1", "time": 1.0, "length": 0.5, "pitch": 60, "text": "", "end_word": true}
    ]
  }
}
```

The project snapshot contains current notes, draft lyrics and metadata, including
media paths. Treat it as input, not permission to modify source files. This enables
future transcription/alignment plugins to return lyrics on existing notes rather
than only create new notes. Keep stable note IDs when annotating existing notes.
No current project is changed until the user explicitly accepts a validated result.

## Progress, results and errors

Emit newline-terminated, flushed UTF-8 lines on stdout:

```text
OPENLIPS_PLUGIN:{"progress": 25, "message": "Analyzing audio locally"}
```

Messages update the status; the progress indicator is indeterminate during work,
then complete on success. Other stdout/stderr lines appear in the bounded log.
Do not print secrets. Exit nonzero on failure, with an actionable error message.
Studio can terminate the worker on cancellation; do not spawn detached child
processes, because child-process-tree cancellation is not provided yet.

On success write `result.json` inside the job directory and exit 0. It uses the
project JSON schema above, including a `notes` array. Notes require nonnegative
finite `time`, positive finite `length`, integer MIDI `pitch` 0..127, optional
`text`, `end_word`, `line_break_after`, `page_break_time`, and unique `id` (generated
if omitted). Preserve phrase fields when editing an existing chart. Limits are
64 MiB and 100,000 notes. Embedded NUL characters, bad timings and duplicate IDs
are rejected. An empty draft is not accepted by the current GUI.

Optional `draft.mid` enables MIDI export. Neither result file may resolve outside
the job directory. Never modify original inputs. Job files are temporary; the
user must accept/export before closing the dialog.

Current result capability: **note-draft**, meaning notes, syllables and phrase
fields are previewed then replace editor notes as one undoable action. Studio
preserves its title/artist, lyric draft and existing reference media. Processing
plugins can return modified copies of existing notes. There are no arbitrary
editor widgets, live audio callbacks, unrestricted host commands or export hooks.
New capability types should be explicitly versioned, not smuggled into this schema.

## Build a package

Layout:

```text
openlips-plugin.json
README.md
LICENSE
runtime/MyWorker/MyWorker[.exe]
runtime/MyWorker/... private dependencies and models ...
```

Stage only redistributable plugin files in an ignored build directory. Include
dependency/model licenses and version inventories. Build the native executable on
the target OS. Package it with:

```sh
python -m tools.package_studio_plugin build/my-plugin --out release_assets/my-plugin-windows-x64.opl
```

The tool creates a ZIP without overwriting existing output. API-2 packages support
up to 2 GiB compressed and unpacked, and 50,000 entries. Paths, case-insensitive
duplicates, reserved Windows names, special files and encrypted entries are
rejected. Unix executable bits and safe internal symlinks are preserved; no entry
may be extracted below a symlink. Escaping/dangling/cyclic links fail installation
with rollback. Windows packages should avoid symlinks, which may require elevated
privileges. Large packages install in a background thread; forced cancellation of
an installation is not supported, so wait for completion before closing.

Build/test an actual `.opl` on a clean machine, not just a source worker. CI tests
Basic Pitch by installing the package into an isolated directory, running real
inference through the frozen GUI, previewing, accepting, undoing and redoing.
The Studio archive must remain usable without any plugin installed.

## Examples and backward compatibility

- [Basic Pitch](../plugins/basic_pitch/): complete independent ML worker.
- [Example lyric mapping](../plugins/example_lyrics/): dependency-free processing
  worker that maps text-file words to existing notes, without claiming AI alignment.
- [Legacy Python importer](../examples/plugins/first-importer/): API-1 example.

API-1 `openlips_studio.importers` entry points and trusted Python folders remain
supported. They import host Python code on activation, unlike API-2 workers, and
keep the smaller 16 MiB / 256-entry package limit with no symlinks. They are not
appropriate for incompatible ML dependency stacks. Neither API is sandboxed.

## Credits

Basic Pitch and its model: Copyright 2022 Spotify AB, Apache-2.0, developed by
Spotify's Audio Intelligence Lab and contributors. The integration is independent,
not a Spotify service or endorsement. See [Basic Pitch](https://github.com/spotify/basic-pitch),
[ONNX Runtime](https://github.com/microsoft/onnxruntime), shipped plugin inventories
and [third-party notices](../THIRD_PARTY_NOTICES.md).
