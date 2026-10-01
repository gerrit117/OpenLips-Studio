# Studio media preparation

The GUI now prepares media via **Datei > OG-Medien konvertieren**. This is an
OG ASF authoring path, not a claim that ASF can replace DLC xWMA assets.
Existing originals and the known-working game installation are never changed.

## Sources and soundtrack

- Video mode uses the selected video and its own soundtrack. Loading a new
  video clears a previously selected reference audio track; choosing separate
  audio afterwards is still possible for editor comparison.
- Audio mode uses the selected audio, producing an audio-only ASF `.wma`.
- Cover-video mode uses the audio plus a static cover. An explicitly selected
  FFmpeg executable creates an H.264/AAC intermediate; the native encoder then
  creates the final VC-1/WMA Pro ASF. Both exported audio and video use the same
  intermediate soundtrack. This intermediate involves an extra lossy audio pass.
- Each preparation creates `song.wma`, optional `song.wmv`, `cover.jpg` and a
  diagnostic `media.json` in a new output directory. Failed jobs do not publish
  partially prepared directories. Encoding runs off the GUI thread.

The accepted Shape of You OG test movie contains **embedded WMA Pro audio**;
OG also contains separate audio-only ASF assets. We cannot infer that every
Lips generation always reads a separate full-song xWMA or always reads movie
audio. DLC preview/full-audio assets and their runtime dispatch are separate
work. A silent video without an audio stream is rejected by this preparation
path rather than paired silently with unrelated audio.

## Encoding and platform limits

The Windows bundle includes the OpenLips native Media Foundation encoder,
built from `tools/media/transcode_windows.cpp`, with no Xbox SDK dependency.
It writes WVC1/VC-1 Advanced video at **768 x 432**, 24000/1001 fps, approximately
2 Mbit/s, and 48 kHz stereo 192 kbit/s 16-bit WMA Pro. This is below the requested
720p ceiling. Final header validation rejects video exceeding 1280 x 720.
720p output itself is not exposed as verified: the accepted profile is 432p.
The previously validated bounded ASF header normalization remains mandatory.

FFmpeg is used only for the optional cover-video intermediate, not to substitute
WMV2/WMA2 for the accepted codecs. It is not bundled automatically; choose a
trusted executable or install one on PATH. The native final encoder currently
requires Windows. macOS/Linux support editing, projects, chart export and covers,
but refuse final media encoding instead of emitting an incompatible format.

ASF outputs are **not** RIFF/xWMA DLC files. The experimental DLC export still
requires separately prepared xWMA full audio and preview; it does not automatically
use these new ASF outputs. `media.json` is an internal preparation report, not
a game song-registration database. There is not yet a one-click registered
OG/DLC song export combining all these steps.

## Covers

Six of six available original DLC jackets are ordinary **256 x 256 JPEGs**:
three songs from the musical pack, I Don't Want To Miss A Thing, Everything
About You and You've Lost That Lovin. Confidence is high for this local DLC
corpus, not for every Lips release. The 40 inspected OG `.jpg` jackets are
wrapped/compressed resources (start `0f f5 12 ed`), not directly readable JPEGs.
Do not simply overwrite them with these DLC JPEGs.

**Cover laden** saves an external image reference in `.olp` and displays a
thumbnail. Export fits the image into a 256 x 256 square, retaining aspect ratio
with a dark background. If no cover is supplied, Studio generates its own
title/artist cover. Every media preparation and every DLC package includes a
cover. DLC export normalizes its cover in temporary staging and references it
through `AlbumJacketUri`; input images are untouched. OG wrapped-cover encoding
and automatic OG cover registration remain unimplemented.

## Synchronization

**Werkzeuge > Alle Noten zeitlich verschieben** shifts note trigger times and
explicit page-switch times together. Positive values move lyrics/notes later;
negative values move them earlier. Negative resulting times are rejected.
This change is undoable, saved in the project, and exported. It does not change
note lengths or pitch and does not add a second GAP conversion to UltraStar.
The existing reference offset remains a preview-only media offset.

## Validation checkpoint

- Existing accepted OG movie path: gameplay confirmed previously; no replacement
  of that checkpoint or extracted game files was performed for this GUI work.
- Three-second synthetic 720p source: video, audio-only and cover-video preparation
  succeed, with normalized 432p WVC1 output and expected WMA Pro headers.
- The full local Shape of You MP3 also converts successfully to audio-only
  WMA Pro ASF; this is an encoding/header check, not a fresh gameplay test.
- Additional synthetic tests cover source selection, read-only inputs, output
  refusal, failed-job rollback, cover/project roundtrip, codec/720p rejection,
  time/page shifting and undo. No copyrighted media is committed.
- Newly added audio-only/cover-video paths and generated DLC cover inclusion
  still need end-to-end gameplay tests. Structural/codec tests are not that proof.
