import struct
import pytest
from PySide6.QtWidgets import QApplication

from studio.tone_preview import pitch_frequency, tone_pcm


def test_reference_pitch_and_pcm():
    assert pitch_frequency(69) == 440
    assert pitch_frequency(81) == 880
    assert pitch_frequency(57) == 220
    samples = struct.unpack('<4800h', tone_pcm(69, .1))
    assert samples[0] == samples[-1] == 0
    assert 0 < max(samples) <= 10000
    crossings = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
    assert abs(crossings - 44) <= 1


@pytest.mark.parametrize('sample_format,width', [('int16', 2), ('int32', 4), ('float', 4), ('uint8', 1)])
def test_output_formats_and_stereo(sample_format, width):
    assert len(tone_pcm(60, .1, channels=2, sample_format=sample_format)) == 4800 * 2 * width


def test_invalid_tones():
    for pitch in (-1, 128, True, 60.5):
        with pytest.raises(ValueError):
            pitch_frequency(pitch)
    with pytest.raises(ValueError):
        tone_pcm(60, float('nan'))


def test_editor_audition_does_not_change_project(monkeypatch):
    from studio.app import StudioWindow
    from studio.model import demo_project
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    window.replace_project(demo_project())
    played = []
    monkeypatch.setattr(window.tones, 'play', lambda pitch, seconds: played.append((pitch, seconds)))
    window.select_note(window.project.notes[0].id)
    before = window.project.to_payload()
    window.audition_note()
    assert played[-1][0] == window.project.notes[0].pitch
    assert window.project.to_payload() == before
    window.pitch_edit.setValue(65)
    assert played[-1][0] == 65
    assert window.project.to_payload() == before
    window.edit_note()
    assert window.note().pitch == 65
    window.hear_notes.setChecked(True)
    window.playing = True
    window.position = window.note().time + .01
    window.update_note_tones()
    assert played[-1][0] == 65
    count = len(played)
    window.update_note_tones()
    assert len(played) == count
    window.dirty = False
    window.close()
