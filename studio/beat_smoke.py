"""Frozen-build check using generated audio, never user media."""
import json
from pathlib import Path
import numpy as np
import soundfile as sf
from studio.model import StudioProject
from studio.beat_dialog import BeatDetection, BeatGridDialog


def run(app, window, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rate = 22050
    audio = np.zeros(rate * 16, dtype=np.float32)
    rng = np.random.default_rng(7)
    pulse = rng.normal(0, .3, 2205) * np.exp(-np.arange(2205) / 180)
    for onset in np.arange(.1, 15.8, .5):
        start = int(onset * rate)
        audio[start:start + len(pulse)] += pulse.astype(np.float32)
    source = output / 'beats.wav'
    sf.write(source, audio, rate)
    project = StudioProject(audio_path=str(source))
    worker = BeatDetection(project, window)
    window.beat_smoke_worker = worker
    result = {}
    worker.ready.connect(lambda bpm, offset, count: result.update(bpm=bpm, offset=offset, count=count))
    worker.failed.connect(lambda error: result.update(error=error))

    def finish():
        (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        dialog = BeatGridDialog(project, window)
        dialog.show()
        dialog.grab().save(str(output / 'settings.png'))
        dialog.reject()
        app.exit(0 if abs(result.get('bpm', 0) - 120) < 4 and result.get('count', 0) >= 20 else 1)

    worker.finished.connect(finish)
    worker.start()
