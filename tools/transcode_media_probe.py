#!/usr/bin/env python3
"""Experimental ASF WMV2/WMA2 conversion; not verified as a Lips media format.

OG reference media uses VC-1/WMA Pro. This alternative requires an isolated
runtime test. Inputs and existing outputs are never overwritten.
"""
from __future__ import annotations

import argparse
import os
import tempfile
from fractions import Fraction
from pathlib import Path


def transcode(source: Path, output: Path, *, width=768, height=432,
              video_bitrate=2_000_000, audio_bitrate=192_000) -> dict:
    import av

    source, output = source.resolve(), output.resolve()
    if source == output or output.exists():
        raise ValueError("output must be a new file, separate from the input")
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("video dimensions must be positive and even")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=output.stem + ".", suffix=".tmp", dir=output.parent)
    os.close(fd)
    temporary = Path(temporary)
    count = {"video_frames": 0, "audio_frames": 0}
    try:
        with av.open(str(source)) as input_file:
            video = next(iter(input_file.streams.video), None)
            audio = next(iter(input_file.streams.audio), None)
            if video is None or audio is None:
                raise ValueError("probe requires one video and one audio stream")
            rate = video.average_rate or Fraction(24000, 1001)
            with av.open(str(temporary), "w", format="asf") as destination:
                vout = destination.add_stream("wmv2", rate=rate)
                vout.width, vout.height, vout.pix_fmt = width, height, "yuv420p"
                vout.bit_rate = video_bitrate
                vout.codec_context.time_base = 1 / rate
                aout = destination.add_stream("wmav2", rate=48000)
                aout.layout = "stereo"
                aout.bit_rate = audio_bitrate
                resampler = av.AudioResampler(format="fltp", layout="stereo", rate=48000)
                last_pts = -1
                for packet in input_file.demux(video, audio):
                    for frame in packet.decode():
                        if packet.stream == video:
                            if frame.pts is None:
                                raise ValueError("video frame has no timestamp")
                            pts = round(Fraction(frame.pts) * frame.time_base * rate)
                            if pts <= last_pts:
                                raise ValueError("video timestamps are not strictly increasing")
                            last_pts = pts
                            converted = frame.reformat(width, height, format="yuv420p")
                            converted.pts, converted.time_base = pts, 1 / rate
                            for encoded in vout.encode(converted):
                                destination.mux(encoded)
                            count["video_frames"] += 1
                        else:
                            for converted in resampler.resample(frame):
                                for encoded in aout.encode(converted):
                                    destination.mux(encoded)
                                count["audio_frames"] += 1
                for frame in resampler.resample(None):
                    for encoded in aout.encode(frame):
                        destination.mux(encoded)
                for stream in (vout, aout):
                    for encoded in stream.encode(None):
                        destination.mux(encoded)
        with av.open(str(temporary)) as check:
            codecs = [s.codec_context.name for s in check.streams]
            if sorted(codecs) != ["wmav2", "wmv2"]:
                raise ValueError(f"unexpected output codecs: {codecs}")
            count.update(bytes=temporary.stat().st_size, duration_us=check.duration,
                         codecs=codecs)
        # Windows rename fails rather than replacing an output created meanwhile.
        if output.exists():
            raise FileExistsError(output)
        temporary.rename(output)
        return count
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = transcode(args.input, args.out)
    print(result)
    print("experimental codecs: runtime acceptance and media/chart sync NOT VERIFIED")


if __name__ == "__main__":
    main()
