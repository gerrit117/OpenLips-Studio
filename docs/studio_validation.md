# First desktop beta validation

Windows 11, Python 3.14.4, PySide6 6.11.2, Mido 1.3.3, QtAwesome 1.4.2,
PyInstaller 6.22.3. Source tests use only synthetic song/MIDI content.

Verified: project roundtrip with external audio/video links; unfinished project
saving without X360 output; MIDI tempo map and channel isolation; stable note
order; explicit lyric assignment; note editing, undo/redo, dragging/resizing;
following cursor moves bars left; standalone template-free X360 export refuses
overwrite; explicit page timestamp serialization and unchanged note starts;
UltraStar text/timing/pitch/numeric phrase breaks preserved.

First frozen executable failed loading QtCore. Root cause: PyInstaller resolved
Qt's unversioned `icuuc.dll` import from a Poppler directory on the developer
PATH. That ICU exports differently named symbols than Windows' ICU shim. The
spec excludes this unrelated bundled ICU; the executable then started and
completed the screenshot smoke test successfully. This did not require changing
the editor or any game/song files.

Screenshots and output files are local under ignored `private/outputs/`.
Local reference MP3 and MP4 playback was tested together: the cursor advanced,
video frames reached QVideoSink and neither decoder reported an error. This is
preview playback validation, not proof of a recording's lyric synchronization.
Both available real UltraStar examples were read locally without modification:
296/487 notes and 38/76 explicit phrase times survived import. No example lyrics
or notes are committed in tests.
No real song is included in the beta artifact. Native STFS tests can be enabled
with `OPENLIPS_STFS_BACKEND`; they otherwise skip rather than simulate acceptance.

68 previously tracked private sample assets were removed from the current Git
index without deleting existing local files. Older Git history still contains
them. Public visibility/release remains gated on that history and license audit.

Not yet established: macOS runtime/audio compatibility, Xbox acceptance of
every newly edited project, exact Lips text-fill animation, custom DLC discovery,
community hosting/moderation, automatic phonetic syllabification and full LS2
authoring. Build workflow existence is not a successful macOS test.
