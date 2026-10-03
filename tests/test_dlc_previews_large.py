"""Synthetic preview timing and larger STFS hash-tree regressions."""
import os
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from studio.dlc_media import preview_start_time, preview_lyrics, bundled_tool
from studio.model import StudioProject, EditorNote
from tools.build_dlc import make_manifest, make_pack_manifest, build_package, verify_stfs


def test_manual_preview_window_and_project_roundtrip(tmp_path):
    from studio.model import save_project, load_project
    project = StudioProject(preview_start=12.5, preview_length=4,
        notes=[EditorNote(1, 1, 60, 'First'), EditorNote(13, 1, 60, 'Chosen'),
               EditorNote(17, 1, 60, 'Outside')])
    assert preview_start_time(project) == 12.5
    assert preview_lyrics(project) == 'Chosen'
    path = tmp_path / 'preview.olp'
    save_project(project, path)
    loaded = load_project(path)
    assert (loaded.preview_start, loaded.preview_length) == (12.5, 4)
    old = project.to_payload()
    del old['preview_start'], old['preview_length']
    legacy = StudioProject.from_payload(old)
    assert legacy.preview_start is None and legacy.preview_length == 15


@pytest.mark.parametrize('start,length', [(-1, 15), (float('nan'), 15),
    (0, 0), (0, float('inf'))])
def test_invalid_preview_settings(start, length):
    with pytest.raises(ValueError, match='Preview'):
        StudioProject(preview_start=start, preview_length=length).validate()


def test_preview_controls_and_midi_file_picker(monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog
    from studio.preview_dialog import PreviewDialog
    from studio.song_wizard import SongWizard
    app = QApplication.instance() or QApplication([])
    dialog = PreviewDialog(StudioProject(notes=[EditorNote(5, 1, 60, 'First')]))
    assert dialog.values() == (None, 15)
    assert not dialog.start.isEnabled()
    dialog.automatic.setChecked(False)
    dialog.start.setValue(9)
    dialog.length.setValue(7)
    assert dialog.values() == (9, 7)
    assert dialog.start.isEnabled()
    wizard = SongWizard()
    seen = []
    monkeypatch.setattr(QFileDialog, 'getOpenFileName',
        lambda parent, title, directory, filters: (seen.append(filters) or '', ''))
    for row in (1, 2):
        wizard.choices.setCurrentRow(row)
        wizard.update_fields(1)
        wizard.browse(wizard.rows['chart'][0], '')
        assert wizard.rows['chart'][2].text() == 'MIDI'
    wizard.choices.setCurrentRow(0)
    wizard.browse(wizard.rows['chart'][0], '')
    assert seen == ['MIDI (*.mid *.midi)', 'MIDI (*.mid *.midi)', 'UltraStar (*.txt)']
    dialog.close()
    wizard.close()


def test_preview_starts_at_first_actual_lyric_not_first_file_note():
    project = StudioProject(notes=[EditorNote(9, 1, 60, 'Hi', end_word=False),
        EditorNote(3, 1, 60, '~'), EditorNote(10, 1, 62, '~'),
        EditorNote(11, 1, 64, 'there'), EditorNote(25, 1, 60, 'Not in preview')])
    assert preview_start_time(project) == 9
    assert preview_lyrics(project) == 'Hi there'
    with pytest.raises(ValueError, match='No lyric'):
        preview_start_time(StudioProject())


def test_preview_video_manifest_and_pack_references():
    assets = dict(chart='one.X360', lyric='one_Lyric.X360', audio='one.xWMA',
        preview_audio='one_prv.xWMA', jacket='one.jpg', video='one.wmv',
        preview_video='one_prv.wmv')
    root = ET.fromstring(make_manifest('One', 'Test', 1, 30, assets, preview_lyric='Hello & world'))
    assert root.findtext('MusicVideos/MusicVideo/PreviewVideoUri') == 'one_prv.wmv'
    assert root.findtext('MusicIndices/MusicIndex/PreviewLyric') == 'Hello & world'
    second = {k: v.replace('one', 'two') for k,v in assets.items()}
    songs = [dict(title='One', artist='Test', uint_id=1, duration=30, assets=assets),
             dict(title='Two', artist='Test', uint_id=2, duration=30, assets=second)]
    pack = ET.fromstring(make_pack_manifest(songs, 3))
    assert [v.findtext('PreviewVideoUri') for v in pack.findall('MusicVideos/MusicVideo')] == ['one_prv.wmv', 'two_prv.wmv']
    assert make_manifest('One', 'Test', 1, 30, {k:v for k,v in assets.items() if k not in ('video','preview_video')})


@pytest.mark.skipif(not os.environ.get('OPENLIPS_STFS_BACKEND'), reason='native backend required')
@pytest.mark.parametrize('blocks', [28900, 28901, 29070, 57800, 57801])
def test_native_larger_hash_tree_boundaries(tmp_path, blocks):
    source = tmp_path / 'zeros.dat'
    # Two additional blocks belong to DLC.xml and the file table.
    with source.open('wb') as stream:
        stream.truncate((blocks - 2) * 4096)
        for number in (0, 168, 169, 170, 28897, 28898, 28899, 29068, 57797, 57798):
            if number < blocks - 2:
                stream.seek(number * 4096)
                stream.write(f'unique synthetic block {number}'.encode('ascii'))
    package = tmp_path / 'large.LIVE'
    result = build_package(os.environ['OPENLIPS_STFS_BACKEND'], {'zeros.dat': source},
        b'<DLCContents/>', package, 'Synthetic larger package')
    assert result['allocated_blocks'] == blocks
    assert result['hash_level'] == (1 if blocks == 28900 else 2)
    table_offset = 0xB000 + ((1 + 0x718F) * 4096 if blocks > 28900 else 0)
    with package.open('r+b') as stream:
        stream.seek(table_offset)
        original = stream.read(1)
        stream.seek(table_offset)
        stream.write(bytes([original[0] ^ 1]))
    with pytest.raises(ValueError, match='table hash'):
        verify_stfs(package)


@pytest.mark.skipif(os.environ.get('OPENLIPS_TEST_NATIVE_DLC') != '1', reason='Windows media encoder required')
@pytest.mark.parametrize('start,length', [(None, 15), (8, 10)])
def test_native_preview_uses_requested_source_offset(tmp_path, monkeypatch, start, length):
    from PySide6.QtWidgets import QApplication
    from studio.dlc_media import prepare_dlc_media
    from studio.media import ffmpeg_encoder
    from tools.analyze_asf import inspect
    if os.environ.get('OPENLIPS_TEST_MEDIA_ENCODER'):
        monkeypatch.setattr('studio.dlc_media.native_encoder', lambda: os.environ['OPENLIPS_TEST_MEDIA_ENCODER'])
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'source.mp4'
    ffmpeg = ffmpeg_encoder()
    subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
        'color=c=red:size=320x180:rate=24:duration=24', '-f', 'lavfi', '-i',
        r'aevalsrc=if(lt(t\,5)\,0\,sin(2*PI*660*t)):s=48000:d=24',
        '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-c:a', 'aac', str(source)],
        stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=120)
    project = StudioProject(title='Synthetic', artist='Test', video_path=str(source),
        preview_start=start, preview_length=length,
        notes=[EditorNote(5, 1, 60, 'First'), EditorNote(7, 1, 62, 'word')])
    media, duration = prepare_dlc_media(project, tmp_path / 'media')
    assert abs(duration - 24) < .2
    video = next(s for s in inspect(media['preview_video'])['streams'] if s['kind'] == 'video')
    assert (video['width'], video['height']) == (240, 136)
    raw = subprocess.run([ffmpeg, '-v', 'error', '-i', str(media['preview_audio']),
        '-t', '0.2', '-f', 's16le', '-ac', '1', '-ar', '48000', '-'],
        stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=120).stdout
    import array
    samples = array.array('h', raw)
    assert max(abs(s) for s in samples[4000:]) > 1000  # Not the silent intro.
    probe = subprocess.run([bundled_tool('ffprobe'), '-v', 'error', '-show_entries',
        'format=duration', '-of', 'default=nw=1:nk=1', str(media['preview_video'])],
        stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=120)
    assert abs(float(probe.stdout) - length) < .6
