from pathlib import Path

import pytest

from tools import build_mpeg4_codec_tests as probe


def setup_probe(tmp_path, monkeypatch, *, wrong_audio=False, wrong_tag=False):
    source = tmp_path / 'source.wmv'
    source.write_bytes(b'synthetic-reference')
    ffmpeg = tmp_path / 'ffmpeg'
    ffmpeg.touch()
    commands = []

    def inspect(path):
        tag = next((t for n, _, t in probe.VARIANTS if Path(path).stem == n), 'WVC1')
        if wrong_tag and tag != 'WVC1':
            tag = 'FMP4'
        return dict(streams=[dict(kind='video', fourcc=tag, bitmap_bit_count=24),
                             dict(kind='audio', codec_tag=0x162)])

    def run(command):
        commands.append(command)
        if command[-1] != '-':
            Path(command[-1]).write_bytes(b'synthetic-output')
        return ''

    monkeypatch.setattr(probe, 'inspect', inspect)
    monkeypatch.setattr(probe, 'run', run)
    monkeypatch.setattr(probe, 'audio_hash', lambda _, p: 'changed' if wrong_audio and Path(p) != source else 'same')
    monkeypatch.setattr(probe, 'video_hash', lambda *_: 'same')
    return source, ffmpeg, commands


def test_exact_bitstream_tag_pairs_and_unchanged_audio(tmp_path, monkeypatch):
    source, ffmpeg, commands = setup_probe(tmp_path, monkeypatch)
    report = probe.build(source, tmp_path / 'out', ffmpeg)
    assert len(report['variants']) == 4
    assert all(r['game_acceptance'] == 'not_tested' for r in report['variants'])
    assert source.read_bytes() == b'synthetic-reference'
    encodes = [c for c in commands if '-c:v' in c]
    assert [c[c.index('-c:v') + 1] for c in encodes] == ['copy', 'mpeg4', 'msmpeg4', 'msmpeg4v2']
    assert all(c[c.index('-c:a') + 1] == 'copy' for c in encodes)


@pytest.mark.parametrize('failure', ['wrong_audio', 'wrong_tag'])
def test_failure_does_not_publish(tmp_path, monkeypatch, failure):
    source, ffmpeg, _ = setup_probe(tmp_path, monkeypatch, **{failure: True})
    with pytest.raises(ValueError):
        probe.build(source, tmp_path / 'out', ffmpeg)
    assert not (tmp_path / 'out').exists()
    assert source.read_bytes() == b'synthetic-reference'


def test_refuses_existing_output(tmp_path):
    source = tmp_path / 'source'
    source.touch()
    with pytest.raises(FileExistsError):
        probe.build(source, tmp_path)
