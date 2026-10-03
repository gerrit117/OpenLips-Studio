from studio.media_source import companion_audio


def test_companion_audio_ignores_stems(tmp_path):
    video = tmp_path / 'incorrect-title.mp4'
    video.touch()
    actual = tmp_path / 'Rollercoaster.aac'
    actual.touch()
    (tmp_path / 'incorrect-title [Vocals].aac').touch()
    (tmp_path / 'incorrect-title [Instrumental].aac').touch()
    assert companion_audio(video) == actual
    (tmp_path / 'another-song.mp3').touch()
    assert companion_audio(video) is None


def test_exact_companion_has_priority(tmp_path):
    video = tmp_path / 'song.mp4'
    video.touch()
    audio = tmp_path / 'song.aac'
    audio.touch()
    (tmp_path / 'other.mp3').touch()
    assert companion_audio(video) == audio


def test_video_with_audio_does_not_switch_to_companion(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from studio.media_source import analysis_audio_source
    video = tmp_path / 'song.mp4'
    video.touch()
    (tmp_path / 'song.aac').touch()
    monkeypatch.setattr('studio.dlc_media.bundled_tool', lambda name: 'ffprobe')
    monkeypatch.setattr('studio.media_source.subprocess.run', lambda *args, **kwargs:
        SimpleNamespace(returncode=0, stdout=b'{"streams":[{"index":1}]}'))
    assert analysis_audio_source(video) == str(video)


def test_wizard_audio_mode_accepts_video_file(tmp_path):
    from PySide6.QtWidgets import QApplication
    from studio.song_wizard import SongWizard
    app = QApplication.instance() or QApplication([])
    video = tmp_path / 'song.mp4'
    video.touch()
    wizard = SongWizard()
    wizard.choices.setCurrentRow(3)
    wizard.next()
    wizard.rows['media'][0].setText(str(video))
    wizard.media_kind.setCurrentIndex(wizard.media_kind.findData('audio'))
    assert wizard.validateCurrentPage()
    assert wizard.project.audio_path == str(video)
    assert wizard.project.video_path == ''
    wizard.close()
