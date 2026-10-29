"""Bounded local audio inspection shared by the preparation workflow."""
from pathlib import Path
import copy
import os
import subprocess
import tempfile

from PySide6.QtCore import QThread, Signal

# Krumhansl/Kessler probe-tone profiles; chroma extraction is provided by librosa.
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)


def key_from_chroma(chroma):
    import numpy as np
    values = np.asarray(chroma, dtype=float)
    if values.ndim == 2:
        values = values.mean(axis=1)
    if values.shape != (12,) or not np.isfinite(values).all() or np.std(values) < 1e-6:
        return ''
    names = ('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')
    ranked = [(float(np.corrcoef(values, np.roll(profile, root))[0, 1]), names[root] + suffix)
              for profile, suffix in ((MAJOR_PROFILE, ''), (MINOR_PROFILE, 'm')) for root in range(12)]
    score, name = max(ranked)
    return name if score >= .4 else ''


class SongAnalysis(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)

    def run(self):
        try:
            import numpy as np
            import soundfile as sf
            import librosa
            from studio.media import ffmpeg_encoder
            from studio.media_source import analysis_audio_source
            from studio.beat_grid import detect_beats
            source = analysis_audio_source(self.project.audio_path or self.project.video_path)
            if not Path(source).is_file():
                raise ValueError('No readable song media')
            with tempfile.TemporaryDirectory(prefix='openlips-analysis-') as folder:
                wave = Path(folder) / 'audio.wav'
                result = subprocess.run([ffmpeg_encoder(), '-nostdin', '-v', 'error', '-i', source,
                    '-t', '120', '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '22050', str(wave)],
                    capture_output=True, timeout=90,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if result.returncode:
                    raise ValueError(result.stderr.decode('utf-8', 'replace')[-1200:])
                audio, rate = sf.read(wave, dtype='float32')
            if self.isInterruptionRequested():
                return
            if len(audio) < rate or np.max(np.abs(audio)) < 1e-5:
                raise ValueError('Not enough audible material for analysis')
            output = dict(bpm=None, offset=None, key='', waveform=[], duration=len(audio)/rate, warnings=[])
            try:
                output['bpm'], offset, _ = detect_beats(audio, rate, self.project.bpm)
                output['offset'] = (offset - self.project.reference_offset) % (60/output['bpm'])
            except ValueError as error:
                output['warnings'].append(str(error))
            if self.isInterruptionRequested():
                return
            harmonic = librosa.effects.harmonic(audio)
            output['key'] = key_from_chroma(librosa.feature.chroma_stft(y=harmonic, sr=rate))
            output['waveform'] = [float(np.max(np.abs(chunk))) for chunk in np.array_split(audio, min(1200, len(audio)))]
            if not self.isInterruptionRequested():
                self.ready.emit(output)
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))
