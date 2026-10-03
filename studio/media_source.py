"""Resolve split video/audio imports without guessing between multiple songs."""
from pathlib import Path
import json
import os
import subprocess

AUDIO_EXTENSIONS = {'.aac', '.mp3', '.m4a', '.wav', '.flac', '.ogg', '.wma', '.xwma'}


def companion_audio(path):
    path = Path(path)
    exact = [p for p in path.parent.iterdir() if p.is_file() and
             p.suffix.lower() in AUDIO_EXTENSIONS and p.stem.casefold() == path.stem.casefold()]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None
    candidates = [p for p in path.parent.iterdir() if p.is_file() and
                  p.suffix.lower() in AUDIO_EXTENSIONS and
                  not any(tag in p.stem.casefold() for tag in ('[vocals]', '[instrumental]', '[vocal]'))]
    return candidates[0] if len(candidates) == 1 else None


def analysis_audio_source(path, preferred=''):
    from studio.dlc_media import bundled_tool
    from studio.media import ffmpeg_encoder
    path = Path(path)
    if path.suffix.lower() in AUDIO_EXTENSIONS:
        return str(path)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    probe = bundled_tool('ffprobe')
    if probe:
        result = subprocess.run([probe, '-v', 'error', '-select_streams', 'a',
            '-show_entries', 'stream=index', '-of', 'json', str(path)],
            capture_output=True, timeout=30, creationflags=flags)
        if result.returncode:
            raise ValueError('The selected media file could not be read')
        has_audio = bool(json.loads(result.stdout).get('streams'))
    else:
        result = subprocess.run([ffmpeg_encoder(), '-nostdin', '-v', 'error', '-i', str(path),
            '-map', '0:a:0', '-t', '.02', '-f', 'null', '-'],
            capture_output=True, timeout=30, creationflags=flags)
        has_audio = result.returncode == 0
        if not has_audio and b'matches no streams' not in result.stderr:
            raise ValueError('The selected media file could not be read')
    if has_audio:
        return str(path)
    candidate = Path(preferred) if preferred and Path(preferred).is_file() and Path(preferred) != path else companion_audio(path)
    if candidate is None:
        raise ValueError('This video has no audio track. Select the separate song audio file.')
    return str(candidate)
