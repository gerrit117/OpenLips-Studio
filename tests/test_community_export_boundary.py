import pytest
from studio.exporters import export_community_song, community_reference
from studio.model import StudioProject, EditorNote
from tools.song_bundle import decode_bundle


def test_note_at_exact_media_end_and_youtube_id_not_filename(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    project = StudioProject(title='Boundary', artist='OpenLips', notes=[EditorNote(1, 1, 60, 'Hello')],
        video_reference='abcdefghijk', video_path=str(tmp_path / 'local-video.mp4'))
    target = tmp_path / 'song.ols'
    export_community_song(project, target, duration=2)
    bundle = decode_bundle(target.read_bytes())
    assert bundle.manifest['media']['duration_seconds'] == 2
    assert bundle.manifest['media']['reference_video'] == 'https://www.youtube.com/watch?v=abcdefghijk'
    assert 'local-video' not in target.read_bytes().decode('latin-1')
    project.video_reference = 'song.mp4'
    assert community_reference(project) == ''
    with pytest.raises(ValueError, match='chart|Chart'):
        export_community_song(project, tmp_path / 'short.ols', duration=1)


def test_dialog_defaults_exceed_final_note_and_hide_local_reference(tmp_path):
    from PySide6.QtWidgets import QApplication
    from studio.community_dialog import CommunityExportDialog
    app = QApplication.instance() or QApplication([])
    project = StudioProject(notes=[EditorNote(1, 1, 60, 'Hello')], video_reference='song.mp4')
    dialog = CommunityExportDialog(project)
    assert dialog.duration.value() > project.duration
    assert dialog.fields['youtube'].text() == ''
    dialog.close()


def test_ultrastar_local_filename_is_not_the_youtube_reference(tmp_path):
    from studio.importers import import_ultrastar
    path = tmp_path / 'song.txt'
    path.write_text('#TITLE:Reference\n#ARTIST:OpenLips\n#BPM:120\n#GAP:0\n'
        '#VIDEO:local-video.mp4\n#VIDEOURL:https://youtu.be/abcdefghijk\n: 0 4 0 Hello\nE\n')
    assert import_ultrastar(path).video_reference.endswith('abcdefghijk')
    from studio.media_reference import reference_video
    assert reference_video('v=abcdefghijk,co=cover.jpg').endswith('abcdefghijk')
    assert reference_video('movie.mp4') == ''
