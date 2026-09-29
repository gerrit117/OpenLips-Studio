import math
import struct

import pytest

from tools.build_owned_chart import TRACKS, OG_CLASS_TOKENS, build_owned_pair, validate_owned_chart
from tools.build_lyric_resource import TEXT
from tools.walk_ixb_graph import Graph, GraphError
from tools.write_template_chart import Note, SongChart


def model():
    return SongChart([Note(8, 1, 65, "World", line_break_after=True),
                      Note(5, 0.5, 60, "Hello")])


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
