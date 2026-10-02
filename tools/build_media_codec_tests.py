"""Prepare isolated OG ASF audio-codec probes; never install or overwrite them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from tools.analyze_asf import inspect
from tools.normalize_og_asf import normalize


def run(arguments):
    result = subprocess.run([str(a) for a in arguments], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=7200,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise ValueError(result.stderr.decode('utf-8', errors='replace')[-6000:])
    return result.stdout.decode('utf-8', errors='strict').strip()


def video_hash(ffmpeg, path):
    # Hash concatenated encoded packet payloads, not decoded frames or ASF headers.
    return run([ffmpeg, '-v', 'error', '-i', path, '-map', '0:v:0', '-c:v', 'copy',
                '-f', 'hash', '-hash', 'sha256', '-'])


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def reference_stream_maps(streams):
    """ASF IDs are referenced by the game; FFmpeg assigns them in map order."""
    if len(streams) != 2 or sorted(s['number'] for s in streams) != [1, 2]:
        raise ValueError('Requires exactly two contiguous ASF stream IDs (1, 2)')
    ordered = sorted(streams, key=lambda s: s['number'])
    return [value for s in ordered for value in
            ('-map', {'audio': '0:a:0', 'video': '0:v:0'}[s['kind']])]


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
    stream_maps = reference_stream_maps(original['streams'])
    reference_ids = {s['kind']: s['number'] for s in original['streams']}
    original_sha = file_hash(source)
    encoded_video_hash = video_hash(ffmpeg, source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.codec-tests-', dir=output.parent) as temp:
        stage = Path(temp) / 'ready'
        stage.mkdir()
        shutil.copy2(source, stage / 'original.wmv')
        rows = []
        for name, codec in [('remux-control', 'copy'), ('vc1-wma-standard', 'wmav2')]:
            raw = Path(temp) / (name + '.wmv')
            command = [ffmpeg, '-v', 'error', '-nostdin', '-n', '-i', source,
                       *stream_maps, '-map_metadata', '-1',
                       '-c:v', 'copy', '-c:a', codec]
            if codec != 'copy':
                command += ['-ar', '48000', '-ac', '2', '-b:a', '192k']
            # Match the source's fixed packet size when possible. Other ASF fields
            # may still differ, which is why the remux control is essential.
            packet = original.get('min_packet')
            if packet and packet == original.get('max_packet'):
                command += ['-packet_size', str(packet)]
            command += ['-f', 'asf', raw]
            run(command)
            destination = stage / raw.name
            normalize(raw, destination)
            checked = inspect(destination)
            if {s.get('kind'): s['number'] for s in checked['streams']} != reference_ids:
                raise ValueError('Generated ASF stream IDs differ from the reference')
            expected = 0x162 if codec == 'copy' else 0x161
            audios = [s for s in checked['streams'] if s.get('kind') == 'audio']
            if len(audios) != 1 or audios[0]['codec_tag'] != expected:
                raise ValueError('Unexpected audio codec in generated probe')
            unchanged = video_hash(ffmpeg, destination) == encoded_video_hash
            if not unchanged:
                raise ValueError('Encoded video packet payloads changed; refusing the probe')
            checked['filename'] = str(output / destination.name)
            rows.append(dict(variant=name, filename=destination.name, sha256=file_hash(destination),
                             encoded_video_unchanged=True, audio_codec=codec,
                             game_acceptance='not_tested', asf=checked))
        if file_hash(source) != original_sha:
            raise ValueError('Reference changed during preparation')
        original['filename'] = str(source)
        report = dict(reference=original, reference_sha256=original_sha,
                      reference_stream_ids=reference_ids,
                      encoded_video_hash=encoded_video_hash, variants=rows,
                      source_unchanged=True,
                      warning='Encoding/header checks only. Test original, then remux control, then WMA Standard with the same chart/profile. No game files installed.')
        (stage / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if output.exists():
            raise FileExistsError('Output appeared during preparation')
        # Same-volume directory rename; Windows refuses an existing destination.
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
        print(f"{row['filename']}: audio={row['audio_codec']}, encoded_video_unchanged=True, gameplay=NOT TESTED")
    print(report['warning'])


if __name__ == '__main__':
    main()
