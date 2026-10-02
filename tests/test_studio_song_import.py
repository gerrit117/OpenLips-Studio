import json
from pathlib import Path
import shutil

import pytest

from studio.plugin_song_import import SongImport


def fixture_job(root):
    job = root / 'job'
    job.mkdir()
    (job / 'chart.txt').write_text('#TITLE:Fixture\n#ARTIST:OpenLips\n#BPM:120\n#GAP:0\n: 0 4 0 Hel\n: 4 4 2 lo \nE\n', encoding='utf-8')
    (job / 'audio.wav').write_bytes(b'owned-synthetic-placeholder')
    (job / 'result.json').write_text(json.dumps(dict(format='openlips-plugin-song', schema_version=1,
                                                   chart='chart.txt', audio='audio.wav')), encoding='utf-8')
    return job


def test_song_adoption_keeps_assets_after_job_cleanup(tmp_path):
    job = fixture_job(tmp_path)
    imported = SongImport(job)
    assert len(imported.project.notes) == 2
    result = imported.adopt(tmp_path / 'owned')
    shutil.rmtree(job)
    assert Path(result.audio_path).read_bytes() == b'owned-synthetic-placeholder'
    assert result.title == 'Fixture'
    assert len(result.notes) == 2


@pytest.mark.parametrize('chart', ['../outside.txt', '/absolute.txt', 'missing.txt'])
def test_bad_bundle_path_refused(tmp_path, chart):
    job = fixture_job(tmp_path)
    data = json.loads((job / 'result.json').read_text())
    data['chart'] = chart
    (job / 'result.json').write_text(json.dumps(data))
    with pytest.raises((ValueError, FileNotFoundError)):
        SongImport(job)


def test_import_song_is_undoable_and_does_not_overwrite_previous_project(tmp_path):
    from PySide6.QtWidgets import QApplication
    from studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    window = StudioWindow()
    old_title = window.project.title
    window.path = tmp_path / 'previous.olp'
    result = SongImport(fixture_job(tmp_path)).adopt(tmp_path / 'owned')
    window.apply_plugin_song(result)
    assert window.project.title == 'Fixture'
    assert window.path is None
    assert window.lyrics.toPlainText() == result.lyric_text()
    window.undo()
    assert window.project.title == old_title
    window.redo()
    assert window.project.title == 'Fixture'
    assert Path(window.project.audio_path).is_file()
    window.dirty = False
    window.close()
