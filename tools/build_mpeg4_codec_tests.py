"""Build isolated ASF MPEG-4 probes with unchanged reference audio; never install them."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from tools.analyze_asf import inspect
from tools.build_media_codec_tests import file_hash, run, video_hash

VARIANTS = (('remux-control', 'copy', 'WVC1'),
            ('mpeg4-mp4s', 'mpeg4', 'MP4S'),
            ('msmpeg4v3-mp43', 'msmpeg4', 'MP43'),
            ('msmpeg4v2-mp42', 'msmpeg4v2', 'MP42'))


def audio_hash(ffmpeg, path):
    return run([ffmpeg, '-v', 'error', '-i', path, '-map', '0:a:0',
                '-c:a', 'copy', '-f', 'hash', '-hash', 'sha256', '-'])


def build(source, output, ffmpeg=None):
    from studio.media import ffmpeg_encoder
    source, output = Path(source).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Choose a new output directory')
    ffmpeg = ffmpeg or ffmpeg_encoder()
    if not ffmpeg or not Path(ffmpeg).is_file():
        raise ValueError('FFmpeg executable unavailable')
    original = inspect(source)
    video = [s for s in original['streams'] if s.get('kind') == 'video']
    audio = [s for s in original['streams'] if s.get('kind') == 'audio']
    if len(video) != 1 or video[0]['fourcc'] != 'WVC1' or len(audio) != 1 or audio[0]['codec_tag'] != 0x162:
        raise ValueError('Requires a known-working WVC1/WMA Pro ASF reference')
    source_sha = file_hash(source)
    source_audio = audio_hash(ffmpeg, source)
    source_video = video_hash(ffmpeg, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mpeg4-tests-', dir=output.parent) as temp:
        stage = Path(temp) / 'ready'
        stage.mkdir()
        shutil.copy2(source, stage / 'original.wmv')
        rows = []
        for name, codec, tag in VARIANTS:
            destination = stage / (name + '.wmv')
            command = [ffmpeg, '-v', 'error', '-nostdin', '-n', '-i', source,
                       '-map', '0:v:0', '-map', '0:a:0', '-map_metadata', '-1',
                       '-c:v', codec, '-c:a', 'copy']
            if codec != 'copy':
                # Actual matching bitstreams, no header-tag disguise. Keep source
                # dimensions/rate and disable B-frames for this first legacy probe.
                command += ['-tag:v', tag, '-pix_fmt', 'yuv420p', '-bf', '0',
                            '-g', '24', '-b:v', '2000k']
            packet = original.get('min_packet')
            if packet and packet == original.get('max_packet'):
                command += ['-packet_size', str(packet)]
            command += ['-f', 'asf', destination]
            run(command)
            checked = inspect(destination)
            videos = [s for s in checked['streams'] if s.get('kind') == 'video']
            audios = [s for s in checked['streams'] if s.get('kind') == 'audio']
            if len(videos) != 1 or videos[0]['fourcc'] != tag:
                raise ValueError('Generated video tag does not match intended codec')
            if codec == 'copy' and video_hash(ffmpeg, destination) != source_video:
                raise ValueError('Remux control video packet payloads changed')
            if len(audios) != 1 or audios[0]['codec_tag'] != 0x162 or audio_hash(ffmpeg, destination) != source_audio:
                raise ValueError('Reference audio packet payloads changed')
            if videos[0].get('bitmap_bit_count', 0) == 0:
                raise ValueError('Zero bitmap bit count would fail native predicate')
            run([ffmpeg, '-v', 'error', '-nostdin', '-i', destination,
                 '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'])
            checked['filename'] = str(output / destination.name)
            rows.append(dict(variant=name, filename=destination.name, video_codec=codec,
                             fourcc=tag, sha256=file_hash(destination),
                             encoded_video_unchanged=codec == 'copy',
                             encoded_audio_unchanged=True, ffmpeg_decode='passed',
                             game_acceptance='not_tested', asf=checked))
        if file_hash(source) != source_sha:
            raise ValueError('Reference changed during preparation')
        report = dict(reference_sha256=source_sha, encoded_audio_hash=source_audio,
                      variants=rows, source_unchanged=True,
                      warning='Experimental only; ASF is retained, not MP4. Test original and remux control first. No game files installed; FFmpeg decode is not Lips acceptance.')
        (stage / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if output.exists():
            raise FileExistsError('Output appeared during preparation')
        stage.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path)
    args = parser.parse_args()
    report = build(args.input, args.out, args.ffmpeg)
    for row in report['variants']:
        print(f"{row['filename']}: {row['fourcc']}, audio unchanged, decode passed, gameplay=NOT TESTED")
    print(report['warning'])


if __name__ == '__main__':
    main()
