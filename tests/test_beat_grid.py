import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import copy
import pytest
from studio.model import StudioProject, EditorNote
from studio.beat_grid import points, snap, cut_notes, melisma_selection, trim_overlaps, BeatClock, detect_beats


def test_offset_and_triplets_do_not_move_media():
    p = StudioProject(bpm=120, beat_offset=.1, beat_division=3, reference_offset=2)
    assert snap(p, .43) == pytest.approx(.1 + 2 / 6)
    assert [t for _, t in points(p, 0, .61)] == pytest.approx([.1, .1+1/6, .1+2/6, .6])
    assert p.reference_offset == 2
    assert StudioProject.from_payload(p.to_payload()).beat_offset == .1


def test_grid_cut_retains_duration_and_word_once():
    p = StudioProject(bpm=120, beat_division=2, notes=[EditorNote(.1, .9, 60, 'oh', line_break_after=True)])
    cut_notes(p, [p.notes[0].id])
    assert sum(n.length for n in p.notes) == pytest.approx(.9)
    assert [n.text for n in p.notes] == ['oh', '~', '~', '~']
    assert not any(n.end_word for n in p.notes[:-1])
    assert p.notes[-1].line_break_after
    p.validate()


def test_melisma_keeps_distinct_pitches_and_word_once():
    p = StudioProject(notes=[EditorNote(1, .5, 60, 'oh'), EditorNote(1.5, .5, 64, 'oh')])
    melisma_selection(p, [n.id for n in p.notes])
    assert [n.pitch for n in p.notes] == [60, 64]
    assert p.lyric_text() == 'oh'
    assert p.notes[0].end_word is False
    from studio.model import incomplete_notes
    from studio.exporters import internal_chart
    from tools.build_owned_chart import owned_lyric_payload, build_owned_pair
    assert incomplete_notes(p) == []
    chart = internal_chart(p)
    lyric, _ = owned_lyric_payload(chart)
    assert lyric.decode('utf-8').count('oh') == 1
    assert '~' not in lyric.decode('utf-8')
    chart_bytes, lyric_bytes = build_owned_pair(chart, 'test', 'test.xWMA', bpm=120, song_duration=5)
    assert chart_bytes and lyric_bytes


def test_melisma_rejects_page_crossing():
    p = StudioProject(notes=[EditorNote(1, 1, 60, 'a', line_break_after=True),EditorNote(2,1,64,'b')])
    with pytest.raises(ValueError, match='pages'):
        melisma_selection(p, [n.id for n in p.notes])


def test_polyphonic_trim_is_transactional():
    p = StudioProject(notes=[EditorNote(1, 2, 60),EditorNote(2,1,62),EditorNote(2,1,64)])
    before = copy.deepcopy(p)
    with pytest.raises(ValueError):
        trim_overlaps(p, [n.id for n in p.notes])
    assert p == before


def test_tick_has_no_phantom_click_on_seek():
    p = StudioProject(bpm=120, beat_division=1, beat_offset=.1, beat_enabled=True, beat_ticks=True)
    clock = BeatClock()
    assert clock.tick(p, .3) is None
    assert clock.tick(p, .59) is None
    assert clock.tick(p, .61) == 96
    assert clock.tick(p, .2) is None


def test_real_beat_detector_on_synthetic_clicks():
    import numpy as np
    rate = 22050
    audio = np.zeros(rate*16, dtype=np.float32)
    rng = np.random.default_rng(2)
    pulse = rng.normal(0,.3,1000).astype(np.float32) * np.exp(-np.arange(1000)/100)
    for seconds in np.arange(.1, 15.5, .5):
        start = round(seconds*rate)
        audio[start:start+1000] += pulse
    bpm, offset, count = detect_beats(audio, rate)
    assert abs(bpm - 120) < .5
    assert count >= 20


def test_settings_cancel_and_accept_are_isolated(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from studio.beat_dialog import BeatGridDialog
    app = QApplication.instance() or QApplication([])
    p = StudioProject(notes=[EditorNote(1,1,60,'oh')])
    d = BeatGridDialog(p)
    d.offset.setValue(.2)
    d.reject()
    assert p.beat_offset == 0
    d = BeatGridDialog(p)
    d.offset.setValue(.2)
    d.cut.setChecked(True)
    d.accept()
    assert d.project.beat_enabled and d.project.beat_offset == .2
    assert p.notes[0].length == 1


def test_timing_assistant_creates_grid_lyric_draft():
    from PySide6.QtWidgets import QApplication
    from studio.timing_dialog import TimingDialog
    app = QApplication.instance() or QApplication([])
    d = TimingDialog(StudioProject(bpm=120, beat_division=2, beat_enabled=True, draft_lyrics='one two three'))
    d.grid_lyrics()
    assert [n.time for n in d.notes] == [0, .25, .5]
    assert all(not n.pitch_assigned for n in d.notes)
    d.accept()
    assert d.project.beat_enabled


def test_review_grid_cuts_propagate_and_undo():
    from PySide6.QtWidgets import QApplication
    from studio.guided_review import GuidedReviewDialog
    app = QApplication.instance() or QApplication([])
    original = StudioProject(bpm=120, beat_enabled=True, notes=[EditorNote(1,1,60,'oh')])
    d = GuidedReviewDialog(original)
    d.timeline.selected_ids = {original.notes[0].id}
    d.timeline.cut_selected_grid()
    assert len(d.project.notes) == 8
    assert sum(n.length for n in d.project.notes) == pytest.approx(1)
    assert d.project.lyric_text() == 'oh'
    d.undo()
    assert len(d.project.notes) == 1
    assert len(original.notes) == 1
    d.reject()
