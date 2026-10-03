import math
import struct
from pathlib import Path

import pytest

from tools.build_owned_chart import TRACKS, OG_CLASS_TOKENS, build_owned_pair, validate_owned_chart, offset_notes, midi_to_lips_pitch, owned_lyric_payload
from tools.build_lyric_resource import TEXT
from tools.walk_ixb_graph import Graph, GraphError
from tools.write_template_chart import Note, SongChart, load_json_chart


def model():
    return SongChart([Note(8, 1, 65, "World", line_break_after=True),
                      Note(5, 0.5, 60, "Hello")])


@pytest.mark.parametrize('pitch', range(128))
def test_midi_conversion_is_ascending_not_legacy_raw_index(pitch):
    raw, tone, octave = midi_to_lips_pitch(pitch)
    assert raw == 127 - pitch
    assert tone == pitch % 12
    assert octave == pitch // 12
    assert tone + 12 * octave == pitch


def test_export_preserves_contour_and_exact_note_durations():
    source = SongChart([Note(1, .09, 73, 'One'), Note(2, .7, 66, 'Two'),
                        Note(3, .3, 64, 'Three')])
    chart, _ = build_owned_pair(source, 'Contour', 'Audio/Contour')
    graph = Graph(chart)
    markers = [r for r in graph.records if graph.is_a(r, 'lpsPhraseMarker')]
    for marker, note in zip(markers, source.notes, strict=True):
        time, length, raw, tone, octave = struct.unpack_from('>ffi4xfI', chart, marker.payload+8)
        assert time == pytest.approx(note.time)
        assert length == pytest.approx(note.length)
        assert raw == 127 - note.pitch
        assert tone + 12 * octave == note.pitch


def test_melisma_has_no_literal_tildes_or_duplicate_visible_syllables():
    source = SongChart([Note(1, .2, 60, 'tha', end_word=False),
                        Note(1.2, .2, 62, '~', end_word=False),
                        Note(1.4, .2, 64, '~t'), Note(2, .5, 65, 'way')])
    payload, places = owned_lyric_payload(source)
    text = payload.decode('utf-8')
    assert text == '\ufeff\r\nthat way\r\n'
    assert 1 not in places
    assert text[places[2].offset:places[2].offset+places[2].length] == 't'
    chart, lyric = build_owned_pair(source, 'Melisma', 'Audio/Melisma')
    assert Graph(chart).summary()['melodies'] == 4
    graph = Graph(chart)
    markers = [r for r in graph.records if graph.is_a(r, 'lpsLyricMarker')]
    assert len(markers) == 3
    fragments = []
    for marker in markers:
        _, word = graph.vector(marker, 'm_vecLyricWordData', 20)
        start, size = graph.u32(word, 4), graph.u32(word, 8)
        fragments.append(text[start:start + size])
    assert fragments == ['tha', 't', 'way']
    assert [n.text for n in source.notes] == ['tha', '~', '~t', 'way']
    resource = Graph(lyric).ref(TEXT)
    assert lyric[resource.payload:resource.payload+resource.size] == payload


def test_bare_continuations_keep_notes_without_repeated_lyric_markers():
    source = SongChart([Note(1, .2, 73, 'Yeah', end_word=False),
                        Note(1.2, .3, 71, '~', end_word=False),
                        Note(1.5, .2, 69, '~', end_word=False),
                        Note(1.7, .4, 69, '~', line_break_after=True)])
    chart, _ = build_owned_pair(source, 'Sustain', 'Audio/Sustain')
    graph = Graph(chart)
    melodies = [r for r in graph.records if graph.is_a(r, 'lpsMelodyMarker')]
    lyrics = [r for r in graph.records if graph.is_a(r, 'lpsLyricMarker')]
    assert len(melodies) == 4
    assert len(lyrics) == 1
    assert graph.u32(lyrics[0], 24) == melodies[0].key
    assert graph.u32(lyrics[0], 60) == 1
    _, word = graph.vector(lyrics[0], 'm_vecLyricWordData', 20)
    assert graph.u32(word, 12) == 1
    assert [graph.u32(m, 4) for m in melodies] == [2, 1, 1, 1]
    for marker, note in zip(melodies, source.notes, strict=True):
        assert struct.unpack_from('>ff', chart, marker.payload + 8) == pytest.approx((note.time, note.length))
    corrupted = bytearray(chart)
    struct.pack_into('>f', corrupted, melodies[1].payload + 12, 9)
    with pytest.raises(GraphError, match='melody'):
        validate_owned_chart(bytes(corrupted), owned_lyric_payload(source)[0], source)


def test_intentional_repeated_words_are_not_collapsed():
    source = SongChart([Note(1, .3, 60, 'no'), Note(2, .3, 60, 'no')])
    chart, _ = build_owned_pair(source, 'Repeat', 'Audio/Repeat')
    graph = Graph(chart)
    assert len([r for r in graph.records if graph.is_a(r, 'lpsLyricMarker')]) == 2
    assert owned_lyric_payload(source)[0].decode('utf-8') == '\ufeff\r\nno no\r\n'


def test_orphan_melisma_is_refused():
    with pytest.raises(ValueError, match='preceding lyric'):
        build_owned_pair(SongChart([Note(1, 1, 60, '~')]), 'Bad', 'Audio/Bad')


def test_note_offset_delays_linked_notes_not_media_or_durations():
    source = model()
    shifted = offset_notes(source, 1.5)
    assert source.notes[0].time == 8
    assert shifted.notes[0].time == 9.5
    assert shifted.notes[0].length == source.notes[0].length
    assert shifted.notes[0].pitch == source.notes[0].pitch
    before, lyrics_before = build_owned_pair(source, "Demo", "Audio/Demo",
                                            movie_name="Assets/InGame/Demo", song_duration=30)
    after, lyrics_after = build_owned_pair(shifted, "Demo", "Audio/Demo",
                                          movie_name="Assets/InGame/Demo", song_duration=30)
    assert lyrics_before == lyrics_after
    for name in ('lpsPhraseMarker', 'lpsLyricMarker'):
        a, b = Graph(before), Graph(after)
        ra = [r for r in a.records if a.is_a(r, name)]
        rb = [r for r in b.records if b.is_a(r, name)]
        for old, new in zip(ra, rb, strict=True):
            assert struct.unpack_from('>f', after, new.payload+8)[0] == pytest.approx(
                struct.unpack_from('>f', before, old.payload+8)[0]+1.5)
            assert after[new.payload+12:new.payload+16] == before[old.payload+12:old.payload+16]
    for name in ('ixAudioMarker', 'ixMovieMarker', 'ixSeqTempoCode'):
        a, b = Graph(before), Graph(after)
        old = next(r for r in a.records if a.is_a(r, name))
        new = next(r for r in b.records if b.is_a(r, name))
        assert before[old.payload:old.payload+old.size] == after[new.payload:new.payload+new.size]


@pytest.mark.parametrize('seconds', [math.nan, math.inf, -10])
def test_bad_note_offset_refused(seconds):
    with pytest.raises(ValueError):
        offset_notes(model(), seconds)


def test_fresh_pair_owns_derived_notes_and_named_sorted_sequences():
    chart, lyric = build_owned_pair(model(), "Demo", "Audio/Demo")
    g, lg = Graph(chart), Graph(lyric)
    text = lg.ref(TEXT)
    validate_owned_chart(chart, lyric[text.payload:text.payload + text.size], model())
    assert g.summary()["classes"]["lpsPhraseMarker"] == 2
    assert g.summary()["classes"]["ixSeqSongSectionPatternCode"] == 1
    assert "lpsMelodyMarker" not in g.summary()["classes"]
    for record in g.records:
        if record.class_index:
            name = next(g.lineage(record)).name
            if name in OG_CLASS_TOKENS:
                assert g.u32(record, 0) == OG_CLASS_TOKENS[name]
    root = next(r for r in g.records if g.is_a(r, "lpsChart"))
    package = g.ref(g.u32(root, 24))
    assert g.reference_vector(package, "m_vpAssets", "ixAsset")[1] == [root]
    tracks = g.reference_vector(root, "m_vpSequence", "ixSequence")[1]
    names = []
    for track in tracks:
        info, raw = g.vector(track, "m_strName", 1)
        names.append(chart[raw.payload:raw.payload + info["size"] - 1].decode())
        assert g.u32(track, 24) == 0
        info, listeners = g.vector(track, "m_vpListeners")
        assert (info["size"], info["reserve"], listeners.size) == (0, 32, 128)
        codes = g.reference_vector(track, "m_vpSeqCode", "ixSeqCode")[1]
        times = [struct.unpack_from(">f", chart, c.payload + 8)[0] for c in codes]
        assert times == sorted(times)
    assert names == list(TRACKS)
    lyric_track = next(t for t, n in zip(tracks, names, strict=True) if n == "Lyric")
    lyric_codes = g.reference_vector(lyric_track, "m_vpSeqCode", "ixSeqCode")[1]
    _, first_word = g.vector(lyric_codes[0], "m_vecLyricWordData", 20)
    assert g.u32(first_word, 12) == int(model().notes[1].end_word)
    assert g.u32(root, g.members(root)["m_pIndex"]) == 0
    assert build_owned_pair(model(), "Demo", "Audio/Demo") == (chart, lyric)


@pytest.mark.parametrize("time,length,pitch,text", [
    (-1, 1, 60, "Hi"), (math.nan, 1, 60, "Hi"), (1, math.inf, 60, "Hi"),
    (1, 0, 60, "Hi"), (1, 1, 128, "Hi"), (1, 1, 60, "\0"),
    (1, 1, 60, "\U0001f600"),
])
def test_invalid_notes_rejected(time, length, pitch, text):
    with pytest.raises(ValueError):
        build_owned_pair(SongChart([Note(time, length, pitch, text)]), "Demo", "Audio/Demo")


def test_mapping_corruption_is_detected():
    chart, lyric = build_owned_pair(model(), "Demo", "Audio/Demo")
    g, lg = Graph(chart), Graph(lyric)
    r = next(r for r in g.records if g.is_a(r, "lpsLyricMarker"))
    _, word = g.vector(r, "m_vecLyricWordData", 20)
    modified = bytearray(chart)
    struct.pack_into(">I", modified, word.payload + 4, 0xffffff00)
    text = lg.ref(TEXT)
    with pytest.raises(GraphError, match="mapping"):
        validate_owned_chart(bytes(modified), lyric[text.payload:text.payload + text.size], model())


def test_movie_audio_and_full_duration_are_structurally_owned():
    chart, _ = build_owned_pair(model(), "Amazing", "Levels/Intl/S/Seal/Amazing/Amazing_PV",
                                movie_name="Assets/InGame/Levels/Intl/S/Seal/Amazing/Amazing",
                                song_duration=190.8, audio_start=0.575034,
                                music_start_offset=2.0339,
                                tempo_start=2.0339,
                                time_start=3.777545, time_stop=185.977)
    graph = Graph(chart)
    root = next(record for record in graph.records if graph.is_a(record, "lpsChart"))
    assert struct.unpack_from(">f", chart, root.payload + 88)[0] == pytest.approx(2.0339)
    movie = next(record for record in graph.records if graph.is_a(record, "ixMovieMarker"))
    audio = next(record for record in graph.records if graph.is_a(record, "ixAudioMarker"))
    tempo = next(record for record in graph.records if graph.is_a(record, "ixSeqTempoCode"))
    assert struct.unpack_from(">f", chart, tempo.payload + 8)[0] == pytest.approx(2.0339)
    assert struct.unpack_from(">f", chart, movie.payload + 8)[0] == pytest.approx(0.575034)
    assert struct.unpack_from(">f", chart, audio.payload + 12)[0] == pytest.approx(190.8 - 0.575034)
    assert graph.summary()["graph_errors"] == []


def test_synthetic_clock_fixture_has_time_driven_page_boundaries():
    fixture = Path(__file__).resolve().parents[1] / "examples/synthetic/chart_clock_pages.json"
    model = load_json_chart(fixture)
    data, _ = build_owned_pair(model, "ClockTest", "Audio/ClockTest", song_duration=190.8)
    graph = Graph(data)
    pages = [r for r in graph.records if graph.is_a(r, "lpsPageBreakMarker")]
    times = [struct.unpack_from(">f", data, r.payload + 8)[0] for r in pages]
    assert times == pytest.approx([3.75, 13.75, 23.75, 189.8])
    assert graph.summary()["melodies"] == 6
    root = next(r for r in graph.records if graph.is_a(r, "lpsChart"))
    assert data[root.payload + 32:root.payload + 48] == bytes(16)


def test_dense_phrase_preroll_does_not_cut_previous_notes():
    chart = SongChart([Note(10, 1, 60, "One"),
                       Note(10.5, 0.1, 62, "two", line_break_after=True),
                       Note(11.1, 0.2, 64, "Next")])
    data, _ = build_owned_pair(chart, "Dense", "Audio/Dense")
    graph = Graph(data)
    pages = [r for r in graph.records if graph.is_a(r, "lpsPageBreakMarker")]
    times = [struct.unpack_from(">f", data, r.payload + 8)[0] for r in pages]
    assert times[1] == pytest.approx(11.0)
