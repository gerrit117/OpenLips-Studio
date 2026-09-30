from fractions import Fraction

import pytest

from tools.transcode_media_probe import transcode


def test_refuses_existing_output_and_invalid_dimensions(tmp_path):
    output = tmp_path / "exists.wmv"
    output.write_bytes(b"original")
    pytest.importorskip("av")
    with pytest.raises(ValueError, match="new file"):
        transcode(tmp_path / "input.mp4", output)
    assert output.read_bytes() == b"original"
    with pytest.raises(ValueError, match="positive and even"):
        transcode(tmp_path / "input.mp4", tmp_path / "new.wmv", width=31)


def test_synthetic_audio_video_conversion_and_input_preservation(tmp_path):
    av = pytest.importorskip("av")
    np = pytest.importorskip("numpy")
    source = tmp_path / "synthetic.mkv"
    with av.open(str(source), "w") as container:
        video = container.add_stream("mpeg4", rate=24)
        video.width, video.height, video.pix_fmt = 32, 32, "yuv420p"
        audio = container.add_stream("pcm_s16le", rate=48000)
        audio.layout = "stereo"
        for i in range(24):
            frame = av.VideoFrame.from_ndarray(np.full((32, 32, 3), i * 8, dtype=np.uint8), format="rgb24")
            frame.pts, frame.time_base = i, Fraction(1, 24)
            for packet in video.encode(frame):
                container.mux(packet)
            frame = av.AudioFrame.from_ndarray(np.zeros((1, 4000), dtype=np.int16), format="s16", layout="stereo")
            frame.sample_rate, frame.pts, frame.time_base = 48000, i * 2000, Fraction(1, 48000)
            for packet in audio.encode(frame):
                container.mux(packet)
        for stream in (video, audio):
            for packet in stream.encode(None):
                container.mux(packet)
    original = source.read_bytes()
    output = tmp_path / "probe.wmv"
    result = transcode(source, output, width=32, height=32)
    assert source.read_bytes() == original
    assert sorted(result["codecs"]) == ["wmav2", "wmv2"]
    assert result["video_frames"] == 24
    assert 900000 < result["duration_us"] < 1200000
    assert not list(tmp_path.glob("*.tmp"))


def test_invalid_source_does_not_publish_or_leave_partial(tmp_path):
    pytest.importorskip("av")
    source = tmp_path / "invalid.mp4"
    source.write_bytes(b"not a media file")
    output = tmp_path / "probe.wmv"
    with pytest.raises(Exception):
        transcode(source, output)
    assert not output.exists()
    assert not list(tmp_path.glob("*.tmp"))
