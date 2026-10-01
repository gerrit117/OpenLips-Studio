"""Conservative OG media preparation, separate from experimental DLC encoding.

All output is prepared in a new directory. No source media or game files change.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from tools.analyze_asf import inspect
from tools.normalize_og_asf import normalize


def native_encoder():
    roots = [Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))]
    for root in roots:
        for path in (root / 'media/transcode_windows.exe',
                     root / 'private/runtime/og-framing-test/transcode_windows.exe'):
            if path.is_file():
                return str(path)
    return ''


def ffmpeg_encoder():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    bundled = root / 'media' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
    if bundled.is_file():
        return str(bundled)
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return ''


def run_encoder(arguments, log):
    log(' '.join(str(arg) for arg in arguments))
    result = subprocess.run([str(arg) for arg in arguments], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                            timeout=7200, check=False)
    output = result.stdout.decode('utf-8', errors='replace')
    log(output[-12000:])
    if result.returncode:
        raise ValueError(f'Encoder failed ({result.returncode}): {output[-2000:]}')


def cover_image(project, size=256):
    from PySide6.QtCore import Qt, QRect
    from PySide6.QtGui import QImage, QPainter, QColor, QFont
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor('#25292e'))
    painter = QPainter(image)
    try:
        if project.cover_path:
            source = QImage(project.cover_path)
            if source.isNull():
                raise ValueError('Cover image cannot be decoded')
            scaled = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        else:
            painter.fillRect(0, 0, size, 12, QColor('#3ad5c7'))
            painter.setPen(QColor('#ffffff'))
            font = QFont('Arial', 18)
            painter.setFont(font)
            rect = QRect(18, 28, size - 36, size - 90)
            flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
            while font.pointSize() > 8 and painter.boundingRect(rect, flags, project.title).height() > rect.height():
                font.setPointSize(font.pointSize() - 1)
                painter.setFont(font)
            painter.drawText(rect, flags, project.title)
            painter.setFont(QFont('Arial', 10))
            painter.setPen(QColor('#d1d5da'))
            painter.drawText(QRect(18, size - 65, size - 36, 48), flags, project.artist[:100])
    finally:
        painter.end()
    return image


def write_cover(project, path):
    path = Path(path)
    if path.exists():
        raise FileExistsError('Cover output already exists')
    if not cover_image(project).save(str(path), 'JPEG', 92):
        raise ValueError('Could not write JPEG cover')
    return path


def validate_og_media(path, video):
    result = inspect(path)
    audio = [s for s in result['streams'] if s.get('kind') == 'audio']
    videos = [s for s in result['streams'] if s.get('kind') == 'video']
    if len(audio) != 1 or any(audio[0][key] != value for key, value in
                             [('codec_tag', 0x162), ('rate', 48000), ('channels', 2), ('bits', 16)]):
        raise ValueError('Output is not expected stereo 48 kHz 16-bit WMA Pro')
    if video:
        if len(videos) != 1 or videos[0]['fourcc'] != 'WVC1' or videos[0]['bitmap_bit_count'] != 24:
            raise ValueError('Output is not normalized WVC1')
        if not 0 < videos[0]['width'] <= 1280 or not 0 < videos[0]['height'] <= 720:
            raise ValueError('Video exceeds 1280x720 or has invalid dimensions')
    elif videos:
        raise ValueError('Audio-only output unexpectedly contains video')
    return result


def prepare_media(project, directory, mode, encoder=None, ffmpeg=None, log=lambda text: None):
    """mode is video, audio or cover-video. Video always supplies its own audio."""
    if mode not in ('video', 'audio', 'cover-video'):
        raise ValueError('Unknown media mode')
    if sys.platform != 'win32':
        raise ValueError('The verified VC-1/WMA Pro encoding backend currently requires Windows')
    encoder = encoder or native_encoder()
    ffmpeg = ffmpeg or ffmpeg_encoder()
    if not Path(encoder).is_file():
        raise ValueError('The bundled OpenLips encoder is missing. Extract the complete Windows release archive.')
    source = project.video_path if mode == 'video' else project.audio_path
    if not source or not Path(source).is_file():
        raise ValueError('Select a video for video mode, or audio for audio/cover-video mode')
    directory = Path(directory).resolve()
    if directory.exists():
        raise FileExistsError('Choose a new output folder')
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.openlips-media-', dir=directory.parent) as temp:
        temp = Path(temp)
        ready = temp / 'ready'
        ready.mkdir()
        write_cover(project, ready / 'cover.jpg')
        if mode == 'cover-video':
            if not ffmpeg or not Path(ffmpeg).is_file():
                raise ValueError('The bundled FFmpeg executable is missing. Extract the complete release archive.')
            intermediate = temp / 'cover.mp4'
            run_encoder([ffmpeg, '-nostdin', '-n', '-loop', '1', '-i', ready / 'cover.jpg',
                         '-i', source, '-map', '0:v:0', '-map', '1:a:0', '-vf',
                         'scale=768:432:force_original_aspect_ratio=decrease,pad=768:432:(ow-iw)/2:(oh-ih)/2',
                         '-r', '24000/1001', '-c:v', 'libx264', '-tune', 'stillimage',
                         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k', '-shortest', intermediate], log)
            video_source = intermediate
        else:
            video_source = Path(source)
        # Extract from the same source, not a separately selected soundtrack.
        audio_source = video_source if mode != 'audio' else source
        run_encoder([encoder, audio_source, ready / 'song.wma', '--audio-only'], log)
        audio = validate_og_media(ready / 'song.wma', False)
        files = {'audio': 'song.wma', 'jacket': 'cover.jpg'}
        validation = {'audio': audio}
        if mode != 'audio':
            raw = temp / 'raw.wmv'
            run_encoder([encoder, video_source, raw], log)
            normalize(raw, ready / 'song.wmv')
            validation['video'] = validate_og_media(ready / 'song.wmv', True)
            files['video'] = 'song.wmv'
        manifest = dict(format='openlips-prepared-og-media', version=1, title=project.title,
                        artist=project.artist, mode=mode, assets=files, validation=validation,
                        profile='OG ASF; NOT DLC xWMA',
                        note='Registration in MusicDB/DLC is separate. New audio-only and cover-video paths need gameplay validation.')
        for key, details in validation.items():
            details['filename'] = str(directory / files[key])
        (ready / 'media.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        if directory.exists():
            raise FileExistsError('Output folder appeared during conversion')
        os.rename(ready, directory)
    log(f'Prepared: {directory}')
    return directory
