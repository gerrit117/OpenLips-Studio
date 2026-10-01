from pathlib import Path

import pytest

from tools import build_mpeg4_codec_tests as probe


def setup_probe(tmp_path, monkeypatch, *, wrong_audio=False, wrong_tag=False,
                wrong_stream_ids=False):
    source = tmp_path / 'source.wmv'
    source.write_bytes(b'synthetic-reference')
    ffmpeg = tmp_path / 'ffmpeg'
    ffmpeg.touch()
    commands = []

    def inspect(path):
        tag = next((t for n, _, t in probe.VARIANTS if Path(path).stem == n), 'WVC1')
        if wrong_tag and tag != 'WVC1':
            tag = 'FMP4'
        swapped = wrong_stream_ids and Path(path) != source
        return dict(streams=[dict(kind='video', number=1 if swapped else 2,
                                 fourcc=tag, bitmap_bit_count=24),
                             dict(kind='audio', number=2 if swapped else 1,
                                  codec_tag=0x162)])

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
    assert all([c[i + 1] for i, value in enumerate(c) if value == '-map'] ==
               ['0:a:0', '0:v:0'] for c in encodes)
    assert report['reference_stream_ids'] == {'video': 2, 'audio': 1}


@pytest.mark.parametrize('failure', ['wrong_audio', 'wrong_tag', 'wrong_stream_ids'])
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


def test_preserves_video_first_reference_ids():
    assert probe.reference_stream_maps([dict(kind='audio', number=2),
                                        dict(kind='video', number=1)]) == [
        '-map', '0:v:0', '-map', '0:a:0']


@pytest.mark.parametrize('numbers', [(1, 3), (1, 1)])
def test_refuses_noncontiguous_or_duplicate_ids(numbers):
    with pytest.raises(ValueError, match='stream IDs'):
        probe.reference_stream_maps([dict(kind='audio', number=numbers[0]),
                                     dict(kind='video', number=numbers[1])])
