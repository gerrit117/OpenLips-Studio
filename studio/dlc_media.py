"""Automatic Windows DLC media preparation with checked decoded-packet tables."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from studio.media import ffmpeg_encoder, native_encoder, run_encoder, write_cover, validate_og_media
from tools.normalize_og_asf import normalize
from tools.inventory_media_codecs import inspect_riff
from studio.i18n import tr

PREVIEW_SECONDS = 15.0


def media_streams(path, ffprobe):
    result = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'stream=codec_type',
        '-of', 'json', str(path)], stdin=subprocess.DEVNULL, capture_output=True,
        check=True, timeout=60, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    return {stream['codec_type'] for stream in json.loads(result.stdout).get('streams', [])}


def resolve_audio_source(project, ffprobe):
    candidates = []
    if project.audio_path:
        candidates.append(Path(project.audio_path))
    if project.video_path:
        video = Path(project.video_path)
        candidates.append(video)
        # Syncer commonly stores a silent video beside a same-name soundtrack.
        candidates += [video.with_suffix(ext) for ext in
                       ('.m4a', '.mp3', '.aac', '.wav', '.flac', '.ogg', '.opus', '.wma')]
    for path in dict.fromkeys(candidates):
        if path.is_file() and 'audio' in media_streams(path, ffprobe):
            return str(path)
    raise ValueError(tr('export.no_audio'))


def preview_start_time(project):
    project.validate()
    if project.preview_start is not None:
        return project.preview_start
    entries = [note.time for note in project.notes if note.text.replace('~', '').strip()]
    if not entries:
        raise ValueError('No lyric entry available for the song preview')
    return min(entries)


def preview_lyrics(project):
    start = preview_start_time(project)
    pieces = []
    for note in project.ordered():
        if start <= note.time < start + project.preview_length:
            text = note.text.replace('~', '')
            pieces.append(text)
            if note.line_break_after or note.end_word:
                pieces.append(' ')
    return ''.join(pieces).strip()


def bundled_tool(name):
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    suffix = '.exe' if os.name == 'nt' else ''
    candidates = [root / 'media' / (name + suffix)]
    if not getattr(sys, 'frozen', False):
        candidates += [root / 'private/runtime/dlc-backend-build/Release' / (name + suffix),
                       root / 'private/runtime/usdb-media/extracted/ffmpeg-8.1.2-essentials_build/bin' / (name + suffix)]
    return next((str(path) for path in candidates if path.is_file()), '')


def wave_to_xwma(wave, target, ffmpeg, ffprobe, log):
    wave, target = Path(wave), Path(target)
    info = inspect_riff(wave)
    audio = info['streams'][0]
    if any(audio[key] != value for key, value in
           [('codec_tag', 0x161), ('rate', 48000), ('channels', 2), ('bits', 16)]):
        raise ValueError('Unexpected DLC audio encoder output')
    data_chunk = next(c for c in info['chunks'] if c['tag'] == 'data')
    block = audio['block_align']
    if not block or data_chunk['size'] % block:
        raise ValueError('DLC audio packets are incomplete')
    result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'a:0',
                             '-show_entries', 'frame=nb_samples,pkt_pos', '-of', 'json', str(wave)],
                            stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=7200,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    sizes = [0] * (data_chunk['size'] // block)
    for frame in json.loads(result.stdout)['frames']:
        index = (int(frame['pkt_pos']) - data_chunk['payload_offset']) // block
        if not 0 <= index < len(sizes):
            raise ValueError('Decoded audio frame points outside its packet')
        sizes[index] += int(frame['nb_samples']) * 4
    if not sum(sizes):
        raise ValueError('No decoded audio samples')
    cumulative, total = [], 0
    for size in sizes:
        total += size
        cumulative.append(total)
    raw = wave.read_bytes()
    compressed = raw[data_chunk['payload_offset']:data_chunk['payload_offset'] + data_chunk['size']]
    fmt = struct.pack('<HHIIHHH', 0x161, 2, 48000, audio['avg_bytes_per_sec'], block, 16, 0)
    def chunk(tag, data):
        return tag + struct.pack('<I', len(data)) + data + (b'\0' if len(data) & 1 else b'')
    body = b'XWMA' + chunk(b'fmt ', fmt) + chunk(b'dpds', struct.pack('<' + 'I' * len(cumulative), *cumulative)) + chunk(b'data', compressed)
    with target.open('xb') as stream:
        stream.write(b'RIFF' + struct.pack('<I', len(body)) + body)
    # Header compaction is only accepted when decoding is byte-identical. This
    # checks codec flags and packet boundaries, not just the filename/magic.
    hashes = []
    for source in (wave, target):
        verification = subprocess.run([ffmpeg, '-v', 'error', '-xerror', '-i', str(source),
            '-map', '0:a:0', '-c:a', 'pcm_s16le', '-f', 'hash', '-hash', 'sha256', '-'],
            stdin=subprocess.DEVNULL, capture_output=True, timeout=7200,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if verification.returncode:
            target.unlink(missing_ok=True)
            raise ValueError('Prepared DLC audio did not pass decoding validation')
        hashes.append(verification.stdout.strip())
    if hashes[0] != hashes[1]:
        target.unlink(missing_ok=True)
        raise ValueError('Prepared DLC audio differs after container conversion')
    inspect_riff(target)
    log('DLC audio validated')
    return total / 192000


def prepare_dlc_media(project, directory, log=lambda message: None):
    directory = Path(directory)
    directory.mkdir()
    source = project.video_path or project.audio_path
    if not source or not Path(source).is_file():
        raise ValueError('Add a video or audio file before exporting.')
    if sys.platform != 'win32':
        raise ValueError('Automatic game media conversion is currently available on Windows only.')
    encoder, ffmpeg, ffprobe = native_encoder(), ffmpeg_encoder(), bundled_tool('ffprobe')
    if not all(Path(path).is_file() for path in (encoder, ffmpeg, ffprobe) if path) or not all((encoder, ffmpeg, ffprobe)):
        raise ValueError('The installed media tools are incomplete. Reinstall the full Studio release.')
    source = resolve_audio_source(project, ffprobe)
    media = {'jacket': write_cover(project, directory / 'cover.jpg')}
    preview_start = preview_start_time(project)
    log(f'Preview start: {preview_start:.6f}s, length: {project.preview_length:.6f}s, '
        f'mode: {"first lyric" if project.preview_start is None else "manual"}')
    durations = []
    for label, seconds in (('song', None), ('preview', project.preview_length)):
        log('Preparing ' + label + ' audio')
        pcm = directory / (label + '.wav')
        args = [ffmpeg, '-nostdin', '-n', '-i', source, '-map', '0:a:0', '-vn', '-ar', '48000', '-ac', '2']
        if seconds is not None:
            if preview_start >= durations[0]:
                raise ValueError('The preview starts after the audio ends')
            args += ['-ss', str(preview_start), '-t', str(seconds)]
        run_encoder(args + ['-c:a', 'pcm_s16le', pcm], log)
        asf, wave, target = (directory / (label + suffix) for suffix in ('.wma', '-encoded.wav', '.xWMA'))
        run_encoder([encoder, pcm, asf, '--audio-standard'], log)
        run_encoder([ffmpeg, '-nostdin', '-n', '-i', asf, '-c:a', 'copy', wave], log)
        durations.append(wave_to_xwma(wave, target, ffmpeg, ffprobe, log))
        media['audio' if seconds is None else 'preview_audio'] = target
    if project.video_path:
        log('Preparing video')
        # Decode unsupported input codecs and combine silent video with its audio
        # before sending a conservative H.264/AAC source to Media Foundation.
        prepared_video = directory / 'video-source.mp4'
        args = [ffmpeg, '-nostdin', '-n', '-i', project.video_path, '-i', source,
            '-map', '0:v:0', '-map', '1:a:0', '-vf',
            'scale=768:432:force_original_aspect_ratio=decrease,pad=768:432:(ow-iw)/2:(oh-ih)/2',
            '-r', '24000/1001', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-shortest', prepared_video]
        run_encoder(args, log)
        raw, video = directory / 'raw.wmv', directory / 'song.wmv'
        run_encoder([encoder, prepared_video, raw], log)
        normalize(raw, video)
        validate_og_media(video, True)
        media['video'] = video
        log('Preparing preview video')
        clip = directory / 'preview-source.mp4'
        run_encoder([ffmpeg, '-nostdin', '-n', '-i', prepared_video,
            '-ss', str(preview_start), '-t', str(project.preview_length),
            '-map', '0:v:0', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'fast',
            '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', clip], log)
        raw_preview, preview = directory / 'preview-raw.wmv', directory / 'preview.wmv'
        run_encoder([encoder, clip, raw_preview, '--preview-video'], log)
        normalize(raw_preview, preview)
        validate_og_media(preview, True)
        media['preview_video'] = preview
    return media, durations[0]
