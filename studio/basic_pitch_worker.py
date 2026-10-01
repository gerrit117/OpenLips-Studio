"""Isolated Basic Pitch / ONNX worker. Protocol messages use an explicit prefix."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studio.basic_pitch_plugin import project_from_events, validate_options

PROTOCOL_PREFIX = 'OPENLIPS_PLUGIN:'


def report(progress, message):
    print(PROTOCOL_PREFIX + json.dumps({'progress': progress, 'message': message}), flush=True)


def transcribe(request, output):
    if request.get('protocol') != 1:
        raise ValueError('Unsupported plugin request version')
    source = Path(request['input']).resolve(strict=True)
    options = validate_options(request.get('options', {}))
    report(5, 'Loading Basic Pitch / ONNX')
    from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
    from basic_pitch.inference import predict
    import mido

    report(15, 'Analyzing audio locally')
    _, _, events = predict(
        source, model_or_model_path=build_icassp_2022_model_path(FilenameSuffix.onnx),
        onset_threshold=options['onset_threshold'], frame_threshold=options['frame_threshold'],
        minimum_note_length=options['minimum_note_length'],
        minimum_frequency=440 * 2 ** ((options['minimum_pitch'] - 69) / 12),
        maximum_frequency=440 * 2 ** ((options['maximum_pitch'] - 69) / 12),
        multiple_pitch_bends=False)
    report(90, 'Preparing editable melody draft')
    project = project_from_events(events, source, options['melody_mode'])
    project.notes = [note for note in project.notes if note.length >= options['minimum_note_length'] / 1000]
    if not project.notes:
        raise ValueError('No notes detected. Check pitch limits/thresholds or try an isolated vocal recording.')
    # The exported MIDI represents the filtered editor draft, not the polyphonic raw prediction.
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo', tempo=500000))
    messages = []
    for note in project.notes:
        start = round(mido.second2tick(note.time, 480, 500000))
        end = max(start + 1, round(mido.second2tick(note.time + note.length, 480, 500000)))
        messages.extend([(start, 1, note.pitch), (end, 0, note.pitch)])
    previous = 0
    for tick, on, pitch in sorted(messages):
        track.append(mido.Message('note_on' if on else 'note_off', note=pitch,
                                  velocity=90 if on else 0, time=tick - previous))
        previous = tick
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    midi.save(output / 'draft.mid')
    (output / 'result.json').write_text(json.dumps(project.to_payload(), ensure_ascii=False,
                                                  allow_nan=False), encoding='utf-8')
    report(100, f'{len(project.notes)} notes ready')
    return project


def synthetic_audio(path):
    """Original short harmonic tone sequence, not a song or third-party recording."""
    import math
    import struct
    import wave
    samples = []
    rate = 22050
    for pitch in (60, 64, 67, 72):
        frequency = 440 * 2 ** ((pitch - 69) / 12)
        for index in range(rate):
            t = index / rate
            envelope = min(1, t / .03, (1 - t) / .05)
            value = sum(math.sin(2 * math.pi * frequency * harmonic * t) / harmonic
                        for harmonic in range(1, 5))
            samples.append(round(7000 * envelope * value))
        samples.extend([0] * (rate // 5))
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(struct.pack('<' + 'h' * len(samples), *samples))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    try:
        if args.self_test:
            args.output.mkdir(parents=True, exist_ok=True)
            source = args.output / 'synthetic.wav'
            synthetic_audio(source)
            request = {'protocol': 1, 'input': str(source), 'options': {}}
        else:
            if not args.request or args.request.stat().st_size > 65536:
                raise ValueError('Missing or oversized request')
            request = json.loads(args.request.read_text(encoding='utf-8'))
        project = transcribe(request, args.output)
        if args.self_test:
            detected = {note.pitch for note in project.notes}
            if not {60, 64, 67}.issubset(detected):
                raise ValueError(f'Synthetic self-test did not recover expected pitches: {sorted(detected)}')
        return 0
    except Exception as error:
        report(0, f'Error: {error}')
        print(str(error), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
