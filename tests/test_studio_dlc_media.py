"""Synthetic-only checks for automatic DLC media preparation."""
import hashlib
import os
from pathlib import Path
import subprocess

import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication

from studio.dlc_media import bundled_tool, prepare_dlc_media, resolve_audio_source
from studio.media import ffmpeg_encoder
from studio.model import EditorNote, StudioProject
from tools.inventory_media_codecs import inspect_riff


def test_missing_media_is_rejected(tmp_path):
    with pytest.raises(ValueError, match='video or audio'):
        prepare_dlc_media(StudioProject(), tmp_path / 'media')


@pytest.mark.skipif(os.environ.get('OPENLIPS_TEST_NATIVE_DLC') != '1',
                    reason='Requires Windows native encoder and STFS backend')
@pytest.mark.parametrize('mode', ['audio', 'muxed', 'silent'])
def test_automatic_native_dlc_roundtrip(tmp_path, mode):
    from studio.dlc_dialog import PackageWorker
    from tools.build_dlc import verify_stfs

    app = QApplication.instance() or QApplication([])
    video = mode != 'audio'
    source = tmp_path / ('original.mp4' if video else 'original.wav')
    ffmpeg = ffmpeg_encoder()
    args = [ffmpeg, '-v', 'error', '-nostdin', '-n', '-f', 'lavfi',
            '-i', 'sine=frequency=440:sample_rate=48000:duration=17']
    if video:
        args += ['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=24:duration=17',
                 '-map', '1:v', '-c:v', 'libx264']
        if mode == 'muxed':
            args += ['-map', '0:a', '-c:a', 'aac']
    else:
        args += ['-ac', '2', '-c:a', 'pcm_s16le']
    subprocess.run(args + [str(source)], stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=120)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    soundtrack = source.with_suffix('.m4a')
    if mode == 'silent':
        subprocess.run([ffmpeg, '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
            'sine=frequency=440:sample_rate=48000:duration=17', '-c:a', 'aac', str(soundtrack)],
            stdin=subprocess.DEVNULL, check=True, capture_output=True, timeout=120)
    project = StudioProject(title='Synthetic test', artist='OpenLips',
        notes=[EditorNote(1.0, .5, 60, 'Test'), EditorNote(2.0, 1.0, 64, 'song')],
        video_path=str(source) if video else '', audio_path='' if video else str(source))
    output = tmp_path / 'packages'
    output.mkdir()
    worker = PackageWorker(project, str(output), None)
    errors, completed = [], []
    worker.failed.connect(errors.append)
    worker.completed.connect(completed.append)
    with patch('studio.dlc_pack.secrets.randbits', return_value=1234):
        worker.run()
    assert not errors, errors
    assert len(completed) == 1
    package = Path(completed[0])
    assert package.parent == output
    assert verify_stfs(package)['allocated_blocks'] > 0
    extracted = tmp_path / 'extracted'
    subprocess.run([bundled_tool('openlips_stfs'), 'extract', str(package), str(extracted)],
                   check=True, capture_output=True, timeout=120)
    for name, expected_seconds in [('song.xWMA', 17), ('preview.xWMA', 15)]:
        info = inspect_riff(extracted / name)
        assert info['streams'][0]['codec_tag'] == 0x161
        duration = info['dpds']['last_decoded_bytes'] / 192000
        assert abs(duration - expected_seconds) < .2
    assert (extracted / 'song.wmv').is_file() == video
    assert (extracted / 'custom.X360').is_file()
    assert (extracted / 'custom_Lyric.X360').is_file()
    assert (extracted / 'cover.jpg').is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    previous = package.read_bytes()
    with patch('studio.dlc_pack.secrets.randbits', return_value=5678):
        worker.run()
    assert not errors, errors
    assert len(completed) == 2
    assert package.read_bytes() == previous


def test_silent_video_uses_matching_soundtrack_without_changing_project(tmp_path, monkeypatch):
    video, audio = tmp_path / 'Song.mp4', tmp_path / 'Song.m4a'
    video.write_bytes(b'synthetic-video')
    audio.write_bytes(b'synthetic-audio')
    monkeypatch.setattr('studio.dlc_media.media_streams', lambda path, probe:
                        {'audio'} if path == audio else {'video'})
    project = StudioProject(video_path=str(video))
    assert resolve_audio_source(project, 'probe') == str(audio)
    assert project.audio_path == ''


def test_silent_video_without_audio_has_clear_error(tmp_path, monkeypatch):
    video = tmp_path / 'Song.mp4'
    video.write_bytes(b'synthetic-video')
    monkeypatch.setattr('studio.dlc_media.media_streams', lambda path, probe: {'video'})
    with pytest.raises(ValueError):
        resolve_audio_source(StudioProject(video_path=str(video)), 'probe')
