#!/usr/bin/env python3
"""Experimental OG chart graph, generated without a template heap.

Native OG traces verify clock progression for the four-note pair. A fresh
multi-page pair also switches pages without probes. Audio/catalog registration
remain external; test only in an isolated slot. See docs/og_chart_clock_probe.md.
"""
from __future__ import annotations

import argparse
import math
import struct
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from tools.build_lyric_resource import _schema, build_lyric_ixb
    from tools.build_minimal_ixb_pair import _frame_chunks, _join_ixb, _object, _payload
    from tools.patch_melody_timing import _tone_octave_for_raw_pitch
    from tools.walk_ixb_graph import Graph, GraphError
    from tools.write_template_chart import SongChart, TextPlacement, load_json_chart
except ModuleNotFoundError:
    from build_lyric_resource import _schema, build_lyric_ixb
    from build_minimal_ixb_pair import _frame_chunks, _join_ixb, _object, _payload
    from patch_melody_timing import _tone_octave_for_raw_pitch
    from walk_ixb_graph import Graph, GraphError
    from write_template_chart import SongChart, TextPlacement, load_json_chart


TRACKS = ("Time", "Conductor", "Audio", "Lyric", "Melody", "Group", "Section",
          "CallAndResponse", "Movie", "AudioEffect", "Led")


def midi_to_lips_pitch(pitch: int) -> tuple[int, float, int]:
    """Convert Studio MIDI to the descending file index and ascending Tone.

    The legacy raw-index helper is not a MIDI converter. In the observed
    layout raw_index + fIdx + 12 * octave = 127.
    """
    raw_index = 127 - pitch
    tone, octave = _tone_octave_for_raw_pitch(raw_index)
    return raw_index, tone, octave


def owned_lyric_payload(chart: SongChart):
    """Emit text placements only for syllables, not bare '~' continuations."""
    text = "\ufeff\r\n"
    placements = {}
    previous = None
    for index, note in enumerate(chart.notes):
        fragment = note.text.replace("~", "")
        if fragment:
            place = TextPlacement(len(text), len(fragment))
            text += fragment
            previous = place
            placements[index] = place
        elif previous is not None:
            pass
        else:
            raise ValueError("A melisma continuation needs a preceding lyric fragment")
        if note.line_break_after:
            text += "\r\n"
            previous = None
        elif note.end_word:
            text += " "
    return (text.rstrip(" ") + "\r\n").encode("utf-8"), placements


def owned_lyric_word_ends(chart, placements):
    """A final continuation ends the original syllable without repeating it."""
    ends = {}
    previous = None
    for index, note in enumerate(chart.notes):
        if index in placements:
            previous = index
        if previous is not None:
            ends[previous] = ends.get(previous, False) or note.end_word
        if note.line_break_after:
            previous = None
    return ends


def offset_notes(chart: SongChart, seconds: float) -> SongChart:
    """Shift imported notes and their generated lyric/page timings, not media.

    Positive values delay visible notes relative to video/audio. This is a
    constant alignment adjustment, never a tempo or duration rescaling.
    """
    if not math.isfinite(seconds):
        raise ValueError("note offset must be finite")
    notes = [replace(note, time=note.time + seconds) for note in chart.notes]
    notes = [replace(note, page_break_time=note.page_break_time + seconds)
             if note.page_break_time is not None else note for note in notes]
    if any(not math.isfinite(note.time) or note.time < 0 for note in notes):
        raise ValueError("note offset produces invalid/negative timing")
    return replace(chart, notes=notes)


def phrase_page_starts(notes):
    """Return (previous-note index, page time); None denotes the initial page.

    Explicit page times override preroll, but cannot hide the next phrase's
    initial notes by switching after they have started.
    """
    ordered = sorted(enumerate(notes), key=lambda item: (item[1].time, item[0]))
    if not ordered:
        return []
    pages = [(None, max(0.0, ordered[0][1].time - .8))]
    phrase_end = ordered[0][1].time + ordered[0][1].length
    for (index, previous), (_, following) in zip(ordered, ordered[1:]):
        if previous.line_break_after:
            time = getattr(previous, 'page_break_time', None)
            if time is None:
                time = max(0.0, following.time - .8, min(phrase_end, following.time))
            elif not math.isfinite(time) or not 0 <= time <= following.time:
                raise ValueError(f'Page switch after note {index + 1} must be between 0 and next note start ({following.time:.3f}s)')
            if time < pages[-1][1]:
                raise ValueError('Page switch times must be chronological')
            pages.append((index, time))
            phrase_end = following.time + following.length
        else:
            phrase_end = max(phrase_end, following.time + following.length)
    # UltraStar may close its final line with a timed break. There is no
    # following phrase to display, so keep the ending but emit no new page.
    final_time = getattr(ordered[-1][1], 'page_break_time', None)
    if final_time is not None and (not math.isfinite(final_time) or final_time < 0):
        raise ValueError('Page switch timing must be finite and nonnegative')
    return pages

# Stable first-word file-layout tokens in plain OG charts where present.
OG_CLASS_TOKENS = {
    "lpsChart": 0x3468CD00,
    "ixSequence": 0xECFFF000,
    "ixTempoMap": 0x7C66CD00,
    "ixAudioEffectSequence": 0xA468CD00,
    "lpsLedMasterSequence": 0x0488CD00,
    "ixSeqNameTag": 0x8408F100,
    "ixSeqTempoCode": 0xBC2FD000,
    "ixSeqSongSectionPatternCode": 0xA4B1F200,
    "ixAudioMarker": 0x0422F100,
    "ixMovieMarker": 0x5422F100,
    "lpsPhraseMarker": 0x04A1CD00,
    "lpsLyricMarker": 0x8492CD00,
    "lpsPageBreakMarker": 0xF49DCD00,
    "ixSeqSuspend": 0x6C2FD000,
}


def chart_schema() -> bytes:
    tree = ET.fromstring(_schema("og"))
    ids = {c.attrib["Name"]: i for i, c in enumerate(tree, 1)}

    def add(name, size, base=None, **members):
        attrs = {"Name": name, "Size": str(size)}
        if base:
            attrs["Base"] = str(ids[base])
        cls = ET.SubElement(tree, "Class", attrs)
        fields = ET.SubElement(cls, "Members")
        for field, offset in members.items():
            ET.SubElement(fields, "Member", Name=field, Offset=str(offset))
        ids[name] = len(tree)

    for element in ("ixSequence *", "ixSeqCode *", "unsigned int", "lpsLyricWordData",
                    "ixAudioFXPresetEntrySequence *", "lpsLedSequence *"):
        add(f"ixVector<{element},1,ixAllocator<{element},1>,ixIterator<{element}> >",
            16, _data=0, _reserve=4, _size=8, _allocator=12)
    add("ixPrototype", 56, "ixAsset")
    add("ixAgentPrototype", 72, "ixPrototype", strStateName=56)
    add("ixChart", 92, "ixAgentPrototype", m_vpSequence=72, m_MusicStartOffset=88)
    add("lpsChart", 148, "ixChart", m_strNoiseMaker=92, m_BaseCentOffset=108,
        m_pIndex=112, m_strAudioEffectPresetPath=116, m_strLyricPathCash=132)
    add("ixSequence", 104, "ixAgentPrototype", m_vpSeqCode=72, m_vpListeners=88)
    add("ixTempoMap", 104, "ixSequence")
    add("ixAudioEffectSequence", 120, "ixSequence", m_vecPresetEntrySequences=104)
    add("lpsLedMasterSequence", 124, "ixSequence", m_vecpLedSequence=104, m_bLoop=120)
    add("ixSeqCode", 20, "ixReferencedObject", m_fTriggerTiming=8, m_fLength=12, m_iTrackIndex=16)
    add("ixSeqUtilCode", 20, "ixSeqCode")
    add("ixSeqNameTag", 36, "ixSeqUtilCode", m_strTagName=20)
    add("ixSeqContentSpecific", 20, "ixSeqCode")
    add("ixSeqTempoCode", 44, "ixSeqContentSpecific", m_Tempo=20, m_Numerator=24,
        m_Denominator=28, m_CalculatedMeasure=32, m_CalculatedBeat=36, m_CalculatedTick=40)
    add("ixSeqSongSectionPatternCode", 32, "ixSeqContentSpecific",
        m_Type=20, m_Group=24, m_Pattern=28)
    add("ixSeqMarkerCode", 20, "ixSeqContentSpecific")
    add("ixAudioMarker", 36, "ixSeqMarkerCode", m_strAudioName=20)
    add("ixMovieMarker", 36, "ixSeqMarkerCode", m_strMovieName=20)
    add("lpsMarker", 24, "ixSeqMarkerCode", m_bTriggered=20)
    add("lpsMelodyMarker", 36, "lpsMarker", m_Tone=24, m_bTilt=32)
    add("Tone", 8, fIdx=0, octave=4)
    add("lpsPhraseMarker", 36, "lpsMelodyMarker")
    add("lpsLyricMarker", 64, "lpsMarker", m_pMelodyMarker=24,
        m_vecLyricWordData=28, m_strFreeWord=44, m_bEndOfWord=60)
    add("lpsPageBreakMarker", 24, "lpsMarker")
    add("ixSeqController", 20, "ixSeqCode")
    add("ixSeqSuspend", 20, "ixSeqController")
    return ET.tostring(tree, encoding="utf-8", short_empty_elements=False)


class Emitter:
    def __init__(self):
        self.chunks = []
        self.next_key = 0x06100000

    def key(self):
        self.next_key += 0x100
        return self.next_key

    def raw(self, data):
        key = self.key()
        self.chunks.append(_payload("raw", bytes(data), key))
        return key

    def obj(self, name, body, key=None):
        key = key or self.key()
        if name in OG_CLASS_TOKENS:
            body = bytearray(body)
            struct.pack_into(">I", body, 0, OG_CLASS_TOKENS[name])
        self.chunks.append(_object(name, bytes(body), key=key))
        return key

    def string(self, body, offset, text, reserve=None):
        value = text.encode("utf-8") + b"\0"
        reserve = max(len(value), reserve or 0)
        key = self.raw(value + bytes(reserve - len(value)))
        struct.pack_into(">IIII", body, offset, key, reserve, len(value), 0)

    def refs(self, body, offset, keys):
        reserve = max(32, ((len(keys) + 31) // 32) * 32)
        data = struct.pack(f">{len(keys)}I", *keys) + bytes((reserve - len(keys)) * 4)
        struct.pack_into(">IIII", body, offset, self.raw(data), reserve, len(keys), 0)

    def agent(self, size, name, package=0, root=False):
        body = bytearray(size)
        struct.pack_into(">I", body, 4, 1)
        self.string(body, 8, name)
        struct.pack_into(">II", body, 24, package, 0xff)
        self.string(body, 56, "", 2 if root else 1)
        return body

    @staticmethod
    def code(size, time, length, track=0, refs=1):
        body = bytearray(size)
        struct.pack_into(">Iffi", body, 4, refs, time, length, track)
        return body


def build_owned_pair(chart: SongChart, name: str, audio_name: str, *, bpm=120.0,
                     movie_name: str | None = None,
                     song_duration: float | None = None,
                     audio_start: float = 0.0,
                     music_start_offset: float = 0.0,
                     tempo_start: float = 0.0,
                     time_start: float | None = None,
                     time_stop: float | None = None):
    """Generate one normal-mode OG chart and matching text resource.

    Required-track assumptions are experimental. No duet/short reconstruction,
    no source heap copying, no invented music-index instance.
    """
    if (not chart.notes or not name or not audio_name
            or any("\0" in s for s in (name, audio_name, movie_name or ""))):
        raise ValueError("nonempty notes, name and audio name without nulls required")
    if not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("BPM must be finite and positive")
    if not math.isfinite(audio_start) or audio_start < 0 or not math.isfinite(music_start_offset):
        raise ValueError("invalid audio start or music start offset")
    if not math.isfinite(tempo_start) or tempo_start < 0:
        raise ValueError("invalid tempo start")
    for note in chart.notes:
        if (not math.isfinite(note.time) or not math.isfinite(note.length)
                or note.time < 0 or note.length <= 0 or not 0 <= note.pitch <= 127
                or not note.text or "\0" in note.text):
            raise ValueError("invalid note timing, pitch or text")
        if any(ord(c) > 0xffff for c in note.text):
            raise ValueError("non-BMP lyric offset semantics are not yet verified")
    text, placements = owned_lyric_payload(chart)
    word_ends = owned_lyric_word_ends(chart, placements)
    e = Emitter()
    root, package, chart_key = e.key(), e.key(), e.key()
    sentinel, child, empty = e.key(), e.key(), e.key()
    codes = {name: [] for name in TRACKS}
    last_note_end = max(n.time + n.length for n in chart.notes)
    end = song_duration if song_duration is not None else last_note_end + 3.0
    if not math.isfinite(end) or end <= max(last_note_end, audio_start, tempo_start):
        raise ValueError("song duration must exceed all notes and audio start")
    time_start = audio_start if time_start is None else time_start
    time_stop = end if time_stop is None else time_stop
    if (not all(math.isfinite(x) for x in (time_start, time_stop))
            or not 0 <= time_start < time_stop <= end):
        raise ValueError("invalid Time sequence boundaries")

    def append(track, cls, body):
        key = e.obj(cls, body)
        time = struct.unpack_from(">f", body, 8)[0]
        codes[track].append((time, key))
        return key

    for i, note in enumerate(chart.notes):
        raw_index, tone, octave = midi_to_lips_pitch(note.pitch)
        body = e.code(36, note.time, note.length, raw_index,
                      refs=2 if i in placements else 1)
        struct.pack_into(">fI", body, 24, tone, octave)
        melody = append("Melody", "lpsPhraseMarker", body)
        if i not in placements:
            continue
        word = bytearray(32 * 20)
        place = placements[i]
        # Unknown fields are deliberately zero; this requires runtime testing.
        struct.pack_into(">III", word, 4, place.offset, place.length,
                         int(word_ends[i]))
        body = e.code(64, note.time, note.length, raw_index)
        struct.pack_into(">IIIII", body, 24, melody, e.raw(word), 32, 1, 0)
        struct.pack_into(">I", body, 60, int(word_ends[i]))
        append("Lyric", "lpsLyricMarker", body)
    tags = (("Start", time_start), ("Stop", time_stop)) if movie_name else (
        ("Beat8", 0.0), ("PV Start", time_start), ("PV Stop", time_stop))
    for label, time in tags:
        body = e.code(36, time, 0.08)
        e.string(body, 20, label)
        append("Time", "ixSeqNameTag", body)
    body = e.code(44, tempo_start, 0.0625, 1)
    struct.pack_into(">fII", body, 20, bpm, 4, 4)
    append("Conductor", "ixSeqTempoCode", body)
    body = e.code(32, music_start_offset + 4 * 60 / bpm, 0.1)
    struct.pack_into(">III", body, 20, 0, 1, 1)
    append("Conductor", "ixSeqSongSectionPatternCode", body)
    body = e.code(36, audio_start, end - audio_start)
    e.string(body, 20, audio_name)
    append("Audio", "ixAudioMarker", body)
    if movie_name:
        body = e.code(36, audio_start, 0.064)
        e.string(body, 20, movie_name)
        append("Movie", "ixMovieMarker", body)
    ordered = sorted(enumerate(chart.notes), key=lambda item: (item[1].time, item[0]))
    page_starts = [time for _, time in phrase_page_starts(chart.notes)]
    for time in sorted(set(page_starts + [end - 1.0])):
        append("Section", "lpsPageBreakMarker", e.code(24, time, 0.08))
    append("Section", "ixSeqSuspend", e.code(20, end, 0.08))

    sequence_keys = []
    for track in TRACKS:
        cls, size = {"Conductor": ("ixTempoMap", 104),
                     "AudioEffect": ("ixAudioEffectSequence", 120),
                     "Led": ("lpsLedMasterSequence", 124)}.get(track, ("ixSequence", 104))
        body = e.agent(size, track)
        e.refs(body, 72, [key for _, key in sorted(codes[track])])
        e.refs(body, 88, [])
        if size > 104:
            e.refs(body, 104, [])
        sequence_keys.append(e.obj(cls, body))
    body = e.agent(148, name, package, root=True)
    e.refs(body, 72, sequence_keys)
    struct.pack_into(">f", body, 88, music_start_offset)
    e.string(body, 92, "Set001")
    e.string(body, 116, "Effect01.xml")
    e.obj("lpsChart", body, chart_key)
    e.obj("ixDblCnt<ixPackage *>", struct.pack(">III", 0, empty, empty), empty)
    body = bytearray(72)
    struct.pack_into(">IIIII", body, 4, 1, root, empty, 0, 0)
    e.string(body, 24, "lpsChart")
    struct.pack_into(">I", body, 40, 1)
    e.refs(body, 52, [chart_key])
    e.obj("ixAssetPackage", body, package)
    e.obj("ixDblCnt<ixPackage *>", struct.pack(">III", package, sentinel, sentinel), child)
    e.obj("ixDblCnt<ixPackage *>", struct.pack(">III", 0, child, child), sentinel)
    body = bytearray(52)
    struct.pack_into(">IIIII", body, 4, 1, 0, sentinel, 1, 0)
    e.string(body, 24, name)
    struct.pack_into(">I", body, 40, 1)
    e.obj("ixPackage", body, root)
    schema = chart_schema()
    data, _ = _join_ixb(schema, _frame_chunks(schema, e.chunks), include_num_elements=True)
    validate_owned_chart(data, text, chart)
    return data, build_lyric_ixb(name + "_Lyric", text)


def validate_owned_chart(data, payload, expected):
    graph = Graph(data)
    summary = graph.summary()
    if summary["graph_errors"] or summary["melodies"] != len(expected.notes):
        raise GraphError(f"invalid generated graph: {summary['graph_errors']}")
    text = payload.decode("utf-8")
    owners = set()
    for r in graph.records:
        if not r.class_index:
            continue
        for field in ("m_strName", "strStateName", "m_strTagName", "m_strAudioName",
                      "m_strNoiseMaker", "m_strAudioEffectPresetPath"):
            if field in graph.members(r):
                info, buffer = graph.vector(r, field, 1)
                if buffer is None or buffer.key in owners or buffer.size != info["reserve"]:
                    raise GraphError("missing, aliased or incorrectly sized owned string")
                owners.add(buffer.key)
    markers = [r for r in graph.records if graph.is_a(r, "lpsLyricMarker")]
    expected_payload, placements = owned_lyric_payload(expected)
    word_ends = owned_lyric_word_ends(expected, placements)
    if len(markers) != len(placements):
        raise GraphError("lyric count mismatch")
    expected_text = expected_payload.decode("utf-8")
    melodies = [r for r in graph.records if graph.is_a(r, "lpsMelodyMarker")]
    for r, index in zip(markers, placements, strict=True):
        info, word = graph.vector(r, "m_vecLyricWordData", 20)
        offset, length = graph.u32(word, 4), graph.u32(word, 8)
        place = placements[index]
        if (info["size"] != 1 or (offset, length) != (place.offset, place.length)
                or text[offset:offset + length] != expected_text[place.offset:place.offset + place.length]):
            raise GraphError("generated lyric mapping mismatch")
        melody = graph.ref(graph.u32(r, 24))
        if (melody != melodies[index] or graph.u32(r, 60) != int(word_ends[index])
                or graph.u32(word, 12) != int(word_ends[index])):
            raise GraphError("generated lyric ownership/word boundary mismatch")
    for melody, note in zip(melodies, expected.notes, strict=True):
        raw_index, tone, octave = midi_to_lips_pitch(note.pitch)
        actual = struct.unpack_from(">ffi4xfI", data, melody.payload + 8)
        wanted = (note.time, note.length, raw_index, tone, octave)
        if any(not math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
               for a, b in zip(actual, wanted)):
            raise GraphError("generated melody timing/pitch mismatch")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--audio-name", required=True)
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="new directory; existing directories are never overwritten")
    parser.add_argument("--bpm", type=float, default=120)
    parser.add_argument("--movie-name")
    parser.add_argument("--song-duration", type=float)
    parser.add_argument("--audio-start", type=float, default=0)
    parser.add_argument("--music-start-offset", type=float, default=0)
    parser.add_argument("--tempo-start", type=float, default=0)
    parser.add_argument("--time-start", type=float)
    parser.add_argument("--time-stop", type=float)
    parser.add_argument("--note-offset", type=float, default=0.0,
                        help="seconds added to notes/linked lyrics/pages only; positive delays them")
    args = parser.parse_args()
    if args.note_offset and args.song_duration is None:
        parser.error("--note-offset requires --song-duration so media/end timing stays fixed")
    if Path(args.name).name != args.name or any(c in args.name for c in '/\\:'):
        parser.error("name must be a basename")
    model = offset_notes(load_json_chart(args.input_json), args.note_offset)
    chart, lyric = build_owned_pair(model, args.name,
                                    args.audio_name, bpm=args.bpm,
                                    movie_name=args.movie_name,
                                    song_duration=args.song_duration,
                                    audio_start=args.audio_start,
                                    music_start_offset=args.music_start_offset,
                                    tempo_start=args.tempo_start,
                                    time_start=args.time_start,
                                    time_stop=args.time_stop)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    (args.out_dir / (args.name + ".X360")).write_bytes(chart)
    (args.out_dir / (args.name + "_Lyric.X360")).write_bytes(lyric)
    graph = Graph(chart)
    print(f"chart_bytes={len(chart)} lyric_bytes={len(lyric)} NumOfElements={len(graph.records)}")
    print(f"tracks={','.join(TRACKS)} notes={graph.summary()['melodies']}")
    lengths = sorted(note.length for note in model.notes)
    print(f"note_offset_seconds={args.note_offset:+.6f} media_timing_unchanged=True")
    print(f"note_lengths_seconds: min={lengths[0]:.6f} "
          f"median={lengths[len(lengths)//2]:.6f} max={lengths[-1]:.6f}; "
          "imported durations preserved, no automatic stretching")
    print("fresh ownership graph; no template heap; this output still requires runtime validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
