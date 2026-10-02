"""Prepare a media-free .ols song for the future Studio/community integration."""
import argparse
import json
import os
from pathlib import Path

from tools.song_bundle import encode_bundle, decode_bundle

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart", type=Path, required=True)
    parser.add_argument("--lyric", type=Path, required=True)
    parser.add_argument("--cover", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--artist", required=True)
    parser.add_argument("--album", default="")
    parser.add_argument("--genre", default="")
    parser.add_argument("--language", default="")
    parser.add_argument("--family", choices=("og", "ls2"), default="og")
    parser.add_argument("--duration", type=float)
    parser.add_argument("--youtube")
    parser.add_argument("--offset", type=float, default=0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".ols":
        parser.error("Output must end in .ols")
    metadata = {key: getattr(args, key) for key in ("title", "artist", "album", "genre", "language", "family")}
    inputs = []
    for path, maximum in ((args.chart, 8 * 1024 * 1024), (args.lyric, 8 * 1024 * 1024), (args.cover, 512 * 1024)):
        if path.stat().st_size > maximum:
            parser.error("An input exceeds the supported size")
        inputs.append(path.read_bytes())
    data = encode_bundle(*inputs, metadata=metadata, duration=args.duration, youtube=args.youtube, offset=args.offset)
    with args.out.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(decode_bundle(data).manifest, indent=2, ensure_ascii=False))
    print(f"Wrote {args.out}: no audio/video, original IXB bytes unchanged.")

if __name__ == "__main__":
    main()
