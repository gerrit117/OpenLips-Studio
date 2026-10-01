import math
import pytest

from studio.ai_chart import PitchSpan, WordSpan, notes_from_analysis, words_from_lrc, word_error_rate
from studio.lrc import parse_lrc


def test_word_across_notes_is_not_repeated():
    notes, warnings = notes_from_analysis([PitchSpan(1, 2, 60), PitchSpan(2, 3, 64)],
                                         [WordSpan(1, 3, 'Hello', True)])
    assert [n.text for n in notes] == ['Hello', '']
    assert [n.end_word for n in notes] == [False, True]
    assert notes[-1].line_break_after
    assert any('Word-level' in w for w in warnings)


def test_one_pitch_split_at_supplied_word_boundaries():
    notes, _ = notes_from_analysis([PitchSpan(0, 3, 65)],
                                  [WordSpan(.5, 1.5, 'one'), WordSpan(1.5, 2.5, 'two')])
    assert [(n.time, n.length, n.text) for n in notes] == [(0, .5, ''), (.5, 1, 'one'),
                                                         (1.5, 1, 'two'), (2.5, .5, '')]
    assert all(n.pitch == 65 for n in notes)


def test_unvoiced_word_reported_not_invented():
    notes, warnings = notes_from_analysis([PitchSpan(0, 1, 60)], [WordSpan(2, 3, 'missing')])
    assert len(notes) == 1 and not notes[0].text
    assert any('No usable pitch' in w for w in warnings)


@pytest.mark.parametrize('spans', [[PitchSpan(0, 1, 60), PitchSpan(.5, 2, 62)],
                                  [PitchSpan(math.nan, 2, 60)], [PitchSpan(0, 1, 128)]])
def test_invalid_pitch_rejected(spans):
    with pytest.raises(ValueError):
        notes_from_analysis(spans)


def test_overlap_words_rejected():
    with pytest.raises(ValueError, match='Overlapping'):
        notes_from_analysis([], [WordSpan(0, 2, 'one'), WordSpan(1, 3, 'two')])


def test_lrc_plain_lines_are_not_fake_word_times():
    document = parse_lrc('[00:01]one two\n[00:03]three\n')
    words, warnings = words_from_lrc(document, 5)
    assert [(w.start, w.end, w.text) for w in words] == [(1, 3, 'one two'), (3, 5, 'three')]
    assert len(warnings) == 2


def test_enhanced_lrc_anchors():
    document = parse_lrc('[00:01]<00:01>one <00:02>two\n[00:03]three')
    words, _ = words_from_lrc(document, 5)
    assert [w.start for w in words] == [1, 2, 3]
    assert words[1].phrase_end


def test_wer_with_case_and_punctuation():
    assert word_error_rate('One, two THREE!', 'one two three')['wer'] == 0
    assert word_error_rate('one two three', 'one three')['wer'] == pytest.approx(1 / 3)
    assert word_error_rate('one', 'one two')['wer'] == 1


def test_result_validates_and_round_trips(tmp_path):
    from studio.model import StudioProject, save_project, load_project
    notes, warnings = notes_from_analysis([PitchSpan(0, 1, 65)], [WordSpan(0, 1, 'test')])
    project = StudioProject(notes=notes, warnings=warnings)
    save_project(project, tmp_path / 'test.olp')
    assert load_project(tmp_path / 'test.olp').lyric_text() == 'test'


def test_word_draft_can_use_existing_exporter():
    from studio.exporters import internal_chart
    from studio.model import StudioProject
    notes, warnings = notes_from_analysis([PitchSpan(0, 1, 60), PitchSpan(1, 3, 64)],
                                         [WordSpan(.5, 2.5, 'hello', True)], word_notes=True)
    chart = internal_chart(StudioProject(notes=notes))
    assert len(chart.notes) == 1
    assert chart.notes[0].pitch == 64
    assert chart.notes[0].time == .5 and chart.notes[0].length == 2
    assert 'melismas simplified' in warnings[-2]


def test_lrc_beyond_audio_is_reported():
    words, warnings = words_from_lrc(parse_lrc('[00:01]one\n[01:00]outside'), 5)
    assert [(w.start, w.end) for w in words] == [(1, 5)]
    assert any('Unusable' in w for w in warnings)


def test_ctc_mapping_preserves_display_text_and_word_ranges():
    from studio.ai_alignment import alignment_tokens
    tokens, groups, _ = alignment_tokens('One, TWO!', ['-', '|', 'O', 'N', 'E', 'T', 'W'])
    assert tokens == [2, 3, 4, 1, 5, 6, 2]
    assert groups == [('One,', 0, 3), ('TWO!', 4, 7)]


@pytest.mark.parametrize('text', ['123', 'drei', '', '-' ])
def test_ctc_rejects_unrepresentable_text_without_inventing_tokens(text):
    from studio.ai_alignment import alignment_tokens
    with pytest.raises(ValueError):
        alignment_tokens(text, ['-', '|', 'A', 'B', 'C'])


def test_progress_log_cannot_overwrite_input(tmp_path):
    from tools.create_ai_chart import main
    source = tmp_path / 'original.wav'
    source.write_bytes(b'original-media')
    with pytest.raises(SystemExit):
        main([str(source), '--out', str(tmp_path / 'song.olp'), '--progress-file', str(source)])
    assert source.read_bytes() == b'original-media'


def test_gui_cancel_accept_and_undo(monkeypatch):
    import copy
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    from studio.ai_dialog import AiChartDialog
    from studio.model import StudioProject, EditorNote
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    original = copy.deepcopy(window.project)
    result = StudioProject(notes=[EditorNote(1, .4, 65, 'synthetic')], draft_lyrics='synthetic')
    def cancel(dialog):
        dialog.result_project = result
        return 0
    monkeypatch.setattr(AiChartDialog, 'exec', cancel)
    window.ai_chart_dialog()
    assert window.project == original and not window.history
    def accept(dialog):
        dialog.result_project = result
        return 1
    monkeypatch.setattr(AiChartDialog, 'exec', accept)
    window.ai_chart_dialog()
    assert window.project.notes == result.notes
    assert window.project.title == original.title
    window.undo()
    assert window.project == original
    window.dirty = False
    window.close()


def test_real_bundled_pitch_worker_on_synthetic_audio(tmp_path, monkeypatch):
    import sys
    import time
    import numpy as np
    import soundfile as sf
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QProcess
    from studio.ai_dialog import AiChartDialog
    from studio.model import StudioProject
    class Settings:
        def value(self, key, default='', type=None):
            return default
        def setValue(self, key, value):
            pass
    monkeypatch.setattr('studio.ai_dialog.QSettings', Settings)
    app = QApplication.instance() or QApplication([])
    rate = 16000
    one = np.sin(np.arange(rate) * 2 * np.pi * 220 / rate) * .3
    two = np.sin(np.arange(rate) * 2 * np.pi * 293.6648 / rate) * .3
    path = tmp_path / 'synthetic.wav'
    sf.write(path, np.concatenate((one, np.zeros(rate // 4), two)), rate)
    dialog = AiChartDialog(StudioProject(audio_path=str(path)))
    dialog.runtime.setText(sys.executable)
    dialog.start()
    until = time.monotonic() + 30
    while dialog.worker.state() != QProcess.ProcessState.NotRunning and time.monotonic() < until:
        app.processEvents()
        time.sleep(.01)
    app.processEvents()
    try:
        assert dialog.result_project is not None, dialog.log.toPlainText()
        assert {57, 62} <= {n.pitch for n in dialog.result_project.notes}
        assert dialog.accept_button.isEnabled()
    finally:
        dialog.reject()
