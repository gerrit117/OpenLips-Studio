from pathlib import Path

import pytest

from tools import build_media_codec_tests as probe


def test_existing_output_is_not_touched(tmp_path):
    source = tmp_path / 'source.wmv'
    source.write_bytes(b'synthetic')
    output = tmp_path / 'output'
    output.mkdir()
    with pytest.raises(FileExistsError):
        probe.build(source, output)
    assert source.read_bytes() == b'synthetic'


def test_codec_probe_preserves_source_and_labels_gameplay_unverified(tmp_path, monkeypatch):
    source = tmp_path / 'source.wmv'
    source.write_bytes(b'synthetic')
    ffmpeg = tmp_path / 'fake-ffmpeg'
    ffmpeg.touch()
    output = tmp_path / 'output'
    commands = []

    def inspect(path):
        codec = 0x161 if 'standard' in Path(path).name else 0x162
        return dict(streams=[dict(kind='video', number=2, fourcc='WVC1'),
                             dict(kind='audio', number=1, codec_tag=codec)])

    def run(command):
        commands.append(command)
        if command[-1] == '-':
            return 'SHA256=synthetic-video-hash'
        Path(command[-1]).write_bytes(b'generated-test')
        return ''

    monkeypatch.setattr(probe, 'inspect', inspect)
    monkeypatch.setattr(probe, 'run', run)
    monkeypatch.setattr(probe, 'normalize', lambda src, dst: Path(dst).write_bytes(Path(src).read_bytes()))
    result = probe.build(source, output, ffmpeg)
    assert result['source_unchanged']
    assert all(row['game_acceptance'] == 'not_tested' for row in result['variants'])
    assert (output / 'report.json').is_file()
    assert source.read_bytes() == b'synthetic'
    assert all([c[i + 1] for i, value in enumerate(c) if value == '-map'] ==
               ['0:a:0', '0:v:0'] for c in commands if '-c:a' in c)


def test_video_payload_mismatch_does_not_publish_output(tmp_path, monkeypatch):
    source = tmp_path / 'source.wmv'
    source.write_bytes(b'synthetic')
    ffmpeg = tmp_path / 'fake-ffmpeg'
    ffmpeg.touch()
    output = tmp_path / 'output'
    monkeypatch.setattr(probe, 'inspect', lambda _: dict(streams=[dict(kind='video', number=2, fourcc='WVC1'), dict(kind='audio', number=1, codec_tag=0x162)]))
    monkeypatch.setattr(probe, 'video_hash', lambda _, path: 'original' if Path(path) == source else 'changed')
    monkeypatch.setattr(probe, 'run', lambda command: Path(command[-1]).write_bytes(b'test'))
    monkeypatch.setattr(probe, 'normalize', lambda src, dst: Path(dst).write_bytes(Path(src).read_bytes()))
    with pytest.raises(ValueError, match='video packet'):
        probe.build(source, output, ffmpeg)
    assert not output.exists()
    assert source.read_bytes() == b'synthetic'
