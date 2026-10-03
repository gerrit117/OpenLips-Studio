[English](README.md) | [Deutsch](README.de.md)

![OpenLips](assets/branding/concept-01/openlips-logo-light.png#gh-light-mode-only)
![OpenLips](assets/branding/concept-01/openlips-logo-dark.png#gh-dark-mode-only)

# OpenLips

**Ever wanted to add your own songs to Lips? Even if you haven't, now you can give it a try.**

OpenLips is an independent community project about bringing new songs to the Xbox 360 karaoke game *Lips*. **OpenLips Studio** is the software being built to make that possible: import a song chart, work on its notes and lyrics, and prepare it for the game. You can start with UltraStar or MIDI files, or create a chart yourself.

This is **early-stage development**, not a finished product. There is a working foundation, but plenty is still incomplete, experimental or waiting for more testing.

> **Unofficial and independent.** OpenLips has no affiliation with Microsoft, Xbox or iNiS. You must have the necessary rights to use and share your material. See [rights and responsibility](#independence-rights-and-responsibility).

## Why this exists

I'm Gerrit. I played Lips with friends when I was younger, and for years I've wanted to bring our own songs into it. Eventually, I decided to find out whether that wish could become something real.

Many hours, days and months went into understanding the files, testing ideas, getting things wrong and trying again. The breakthrough was reaching a point where our own chart and lyric files could be created from scratch, then loaded and played by the original Lips (2008) in testing. For the first time in this project, we have both a working result and documentation explaining how we got there.

I originally completed vocational training in information electronics, an IT-related field. I later changed careers and now work as a train driver. My enthusiasm for computers, servers and systems has stayed with me, along with plenty of practical experience. Programming is the part I never properly learned, and my full-time job leaves little room to start from the ground up. AI-assisted development has made it possible for me to turn an idea that kept sitting on the shelf into a project I can actually work on.

As a train driver, I worry about automation too. The thought of being replaced by a computer someday, or just sitting there watching the train drive itself, makes me uneasy. So developers' concerns about what AI might mean for their profession aren't some abstract issue to me. I also understand their concerns about software quality. I don't see their knowledge as replaceable. This project depends on it. Nor is this a one-prompt “make no mistakes” project: there is a lot of research, hands-on testing, debugging and documentation behind it, and mistakes still need to be found and fixed.

That's also why I want to open it up now. I'd love for OpenLips to become more than my personal experiment. If you care about Lips, karaoke, reverse engineering or making useful tools, you're welcome here.

## Help shape it

Something doesn't work? Please [report it](https://github.com/gerrit117/OpenLips-Studio/issues). Tell us what you tried, what happened, which version you used and, if possible, how to reproduce it. Please don't attach copyrighted songs or original game files to public reports.

Ideas, corrections to the documentation, testing on other systems and [pull requests](https://github.com/gerrit117/OpenLips-Studio/pulls) are all welcome. You don't need to write code to contribute. Early feedback is how this project gets better, not an interruption to its development.

## Roadmap

These are plans, not promises about the next release. The first priorities are:

- [x] Add an opt-in plugin manager with `.opl` packages, settings, previews and background import workflows.
- [ ] Document the song format more deeply, including LS2 and later releases.
- [ ] Support quick-time events (QTEs) and other song-specific gameplay actions.
- [ ] Build a community website with accounts and a shared database of user-created charts and lyrics, subject to the necessary rights and moderation.
- [x] Integrate Spotify's [Basic Pitch](https://github.com/spotify/basic-pitch): turn vocal audio into a MIDI and note draft that can be reviewed and edited.
- [ ] Expand the plugin API to additional processing and export workflows.
- [ ] Finish reliable custom DLC installation and discovery, including use with existing profiles.
- [ ] Bring media preparation and song export together into a simpler workflow, and expand conversion support across platforms.
- [ ] Add optional FTP transfer to a compatible Xbox setup.
- [ ] Improve usability, translations, accessibility and real-world testing.

“LS2” is used here as shorthand for Lips releases after the original 2008 game. Their song and DLC layouts still need to be checked individually; they are not assumed to be identical.

Some foundations are already in place:

- [x] Import UltraStar charts and MIDI melodies.
- [x] Edit notes, syllables and phrase boundaries in a graphical editor.
- [x] Save unfinished work as an `.olp` project.
- [x] Generate new chart and lyric files for the original Lips, without a song template.
- [x] Provide native Windows, macOS and Linux beta downloads.

## What Studio can do today

![OpenLips Studio](assets/branding/concept-01/logo-light.png#gh-light-mode-only)
![OpenLips Studio](assets/branding/concept-01/logo-dark.png#gh-dark-mode-only)

- **Import or create.** Bring in UltraStar TXT files, choose a melody track from a MIDI file, or add notes yourself. UltraStar timing and syllables are preserved on import.
- **Start from a recording.** Enable Basic Pitch in the plugin manager, choose an audio file and adjust detection sensitivity, note duration and pitch limits. Review the locally generated draft, save it as MIDI or take its notes into the editor. The analysis can be cancelled; replacing notes can be undone. Isolated vocals work better than a full mix. This is not automatic vocal separation or lyric transcription.
- **Work on the chart.** Create, delete, move or resize notes, change their pitch, assign lyric fragments, set word and phrase endings, and adjust page changes. Undo and redo are available.
- **Create a draft from audio.** Optional local vocal separation, pitch detection and lyric recognition produce an editable chart. Review the result before using it: singing recognition still makes substantial mistakes. Small-model pitch analysis is bundled; the heavier AI engine is a separate download.
- **Keep synchronized lyrics.** Import LRC files and synchronized LRCLIB results, preview line/word timestamps and save them with the project. Exact automatic syllable alignment is still in progress.
- **Check the timing.** Play reference audio or video alongside the chart. Adjust playback speed, zoom in and shift notes and page changes together when the chart needs a timing correction.
- **Check the pitch.** Audition selected notes with a reference tone or enable note tones during playback. Missing optional AI components are downloaded and verified automatically on first use.
- **Save your progress.** An `.olp` project lets you leave a song unfinished and return to it later. Referenced media stays separate.
- **Prepare the presentation.** Choose a cover or generate a simple one. On Windows, DLC export converts the selected video or audio and creates full xWMA audio plus a 15-second preview starting at the first lyric. Video songs also get a small menu preview video. The media tools and STFS backend are included.
- **Export and experiment.** Save a media-free `.ols` Community song or an experimental DLC package. Reliable in-game DLC discovery is still being investigated.
- **Group songs and transfer them.** Export a named song pack from saved projects, or copy a verified DLC directly to an Xbox USB drive with a visible `Content` folder. See the [pack and USB guide](docs/song_packs_usb.md) for current limits and testing status.

![The OpenLips Studio chart editor](assets/screenshots/studio-editor.png)

*The editor with a small original demo chart.*

![Editing a note's timing, pitch, syllable and phrase boundary](assets/screenshots/studio-note-details.png)

*Each note has editable timing, pitch and lyric settings.*

![Basic Pitch parameters and a synthetic note draft](assets/screenshots/studio-plugins.png)

*The first plugin, using an original four-tone test recording rather than a song.*

### What is not ready yet

The confirmed end-to-end tests use the original Lips (2008) through Xenia. Later releases, all gameplay modes and original song events are not fully supported. A working chart export is not yet a finished “import anything and play” workflow, and it does not make unsigned content installable on an unmodified Xbox 360.

Media conversion currently targets the tested original-game path on Windows; editing and chart export are available on macOS and Linux too. Automatic DLC audio conversion, dependable DLC discovery and the community website are still work in progress. If a feature fails, please report it rather than assuming you've done something wrong.

### Media on macOS and Linux

**For now, game export requires already-compatible audio and, if used, video.** MP3/MP4 files can be used as editor references, but are not automatically converted to Lips media on these systems.

The tested original-game video profile is **ASF `.wmv`, VC-1 Advanced (WVC1), 768 × 432 at 24000/1001 fps**, with **48 kHz stereo, 16-bit WMA Pro audio at 192 kbit/s**. Separate OG `.wma` audio uses ASF/WMA Pro. Experimental DLC packaging instead requires **RIFF/XWMA full audio and preview**; renaming `.wma` is not conversion. Video is optional. Original files also contain WMV3 video and WMA Standard/xWMA audio, but those observations do not validate every newly encoded file.

See the [exact media requirements and preparation steps](docs/studio_media.md#already-compatible-media-on-macos-and-linux), including header requirements and the distinction between tested settings and the 720p limit.

## Download

Get the latest beta from **[GitHub Releases](https://github.com/gerrit117/OpenLips-Studio/releases)**. Builds are available for Windows, macOS on Apple Silicon and Intel, and Linux.

Extract the complete Studio archive and keep its files together. Python is included. Basic Pitch is a separate, optional **`.opl`** download for your platform; install it in the plugin manager. Its package includes its own model and analysis runtime, without a separate Python installation, Spotify account or API key. Audio is processed locally, not uploaded. See the [plugin catalog](plugins/README.md), [editor guide](docs/studio.md), [plugin developer guide](docs/studio_plugins.md) and [platform notes](docs/studio_platforms.md).

Windows also has an installer; macOS has a DMG with an Applications shortcut. For optional vocal separation and lyric recognition, extract the **OpenLips-AI** archive and select its `OpenLipsAI` executable in the audio-chart dialog. The larger models download on first use and remain in your local cache. See the [AI workflow and measured limitations](docs/ai_song_creation_test_report.md).

## Documentation

The technical material lives in [`docs/`](docs/). Start with:

- [Using the editor](docs/studio.md).
- [Media, covers and synchronization](docs/studio_media.md).
- [Song-file structures](docs/structures.md) and the [structural reader](docs/og_ixb_reader.md).
- [Page timing and projects](docs/studio_pages_and_community.md).
- [Research and command-line tools](docs/research_overview.md).

The research records both findings and open questions. Reading a format is not the same as safely writing every variant of it.

## Thank you

I couldn't build this without people who learned their craft, wrote these tools and shared their work. Their time and expertise deserve credit, especially in a project like this one.

The app and its development tools rely on [Python](https://www.python.org/), [Qt for Python](https://doc.qt.io/qtforpython-6/), [Mido](https://github.com/mido/mido), [Pyphen](https://github.com/Kozea/Pyphen), [QtAwesome](https://github.com/spyder-ide/qtawesome) and [PyInstaller](https://pyinstaller.org/). [LRCLIB](https://lrclib.net/) supports the optional lyrics search, and [FFmpeg](https://ffmpeg.org/) helps with optional media preparation.

The research and testing also benefited from [Xenia](https://github.com/xenia-project/xenia), [Xenia Canary](https://github.com/xenia-canary/xenia-canary), [Ghidra](https://github.com/NationalSecurityAgency/ghidra) and [XEXLoaderWV](https://github.com/zeroKilo/XEXLoaderWV). The experimental packaging backend builds on [Velocity](https://github.com/hetelek/Velocity) and [Botan](https://botan.randombit.net/). Not all of these tools are included in the application download.

Thank you, too, to everyone who tests a build, reports a bug, shares a useful finding or helps someone else get started. Dependency licenses and notices are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

A special thank you to **Spotify's Audio Intelligence Lab and the authors of [Basic Pitch](https://github.com/spotify/basic-pitch)** for making their transcription model and code available as open source. The independent Basic Pitch plugin uses their work through [ONNX Runtime](https://github.com/microsoft/onnxruntime). It is not a Spotify service or endorsement.

The built-in audio-chart workflow was inspired by [UltraSinger](https://github.com/rakuri255/UltraSinger) and [UltraSinger Studio](https://github.com/lazinessss999-dot/UltraSinger_studio-v1.0). Thank you to their authors, and to the teams behind [Demucs](https://github.com/facebookresearch/demucs), [Whisper](https://github.com/openai/whisper), [faster-whisper](https://github.com/SYSTRAN/faster-whisper) and [SwiftF0](https://github.com/lars76/swift-f0). These are independent local integrations, not affiliated services.

Thank you also to **Markus Böhning and the contributors to [USDB Syncer](https://github.com/bohning/usdb_syncer)**, and to the [yt-dlp](https://github.com/yt-dlp/yt-dlp) team. A separate USDB Downloader plugin is in development, using their existing search/download interface rather than rebuilding it. Native plugin packages and authenticated download testing are still pending.

## Independence, rights and responsibility

**OpenLips and OpenLips Studio are independent, unofficial projects. They are not affiliated with, endorsed by or sponsored by Microsoft, Xbox, iNiS, the developers or publishers of Lips, or any other rights holder.** Product and company names are used only to identify the games and tools involved; their rights remain with their respective owners.

**You are responsible for obtaining and using your source material lawfully.** This includes game files, recordings, videos, cover artwork, lyrics and musical transcriptions. Sharing only a chart or lyrics does not automatically make that material free of copyright. The software grants no additional rights to songs or game content, and owning a recording does not by itself grant redistribution rights.

OpenLips is not a source of game files or commercially released songs. The project's software license does not cover imported content. Please share only content you have the necessary rights to share, and respect the laws that apply where you live.

The project's source code is licensed under [GPL-3.0-or-later](LICENSE).
