"""Exercise frozen inference on generated tones without song data or downloads."""
import argparse
import math
from pathlib import Path
import struct
import subprocess
import wave
from studio.model import load_project


def run(executable, folder, embedded=False):
    folder.mkdir(parents=True, exist_ok=False)
    audio = folder / 'original-tones.wav'
    with wave.open(str(audio), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(b''.join(struct.pack('<h', round(9000 * math.sin(2 * math.pi * hz * n / 16000)))
                                   for hz in (220, 293.6648) for n in range(16000)))
    command = [str(executable)] + (['--ai-worker'] if embedded else [])
    command += [str(audio.resolve()), '--out', str((folder / 'draft.olp').resolve()),
                '--progress-file', str((folder / 'progress.jsonl').resolve())]
    result = subprocess.run(command, timeout=90)
    log = (folder / 'progress.jsonl').read_text(encoding='utf-8')
    if result.returncode:
        raise ValueError(log)
    project = load_project(folder / 'draft.olp')
    if not {57, 62} <= {n.pitch for n in project.notes}:
        raise ValueError('Generated tones were not recovered: ' + log)
    print('Frozen inference recovered both generated pitches; no external Python or model download.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    args = parser.parse_args()
    run(args.executable.resolve(strict=True), args.out, args.embedded)
