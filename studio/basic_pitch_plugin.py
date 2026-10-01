"""Lightweight host adapter. The separately bundled worker owns ML dependencies."""
from pathlib import Path
import sys

from studio.model import EditorNote, StudioProject
from studio.plugins import ImportPlugin, PluginParameter


def worker_command(request, output, python_path=''):
    name = 'OpenLipsBasicPitch.exe' if sys.platform == 'win32' else 'OpenLipsBasicPitch'
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    worker = base / 'plugin-runtime' / 'OpenLipsBasicPitch' / name
    if not getattr(sys, 'frozen', False) and not worker.is_file():
        worker = base / 'dist' / 'OpenLipsBasicPitch' / name
    args = ['--request', str(request), '--output', str(output)]
    if worker.is_file() and not python_path:
        return [str(worker), *args]
    if getattr(sys, 'frozen', False):
        raise ValueError('Basic Pitch runtime is missing or an unsupported custom Python was selected. Extract the complete release archive and clear the Python override.')
    python = python_path or sys.executable
    return [python, str(Path(__file__).with_name('basic_pitch_worker.py')), *args]


def create_plugin():
    return ImportPlugin(
        id='spotify-basic-pitch', label='Basic Pitch', extensions=('.wav', '.flac', '.mp3', '.ogg', '.m4a'),
        import_file=None, create_command=worker_command, author='Spotify Audio Intelligence Lab',
        version='0.4.0', homepage='https://github.com/spotify/basic-pitch',
        description='Vocal-Audio zu einem bearbeitbaren Notenentwurf. Verarbeitung lokal; keine Gesangstrennung.',
        parameters=(
            PluginParameter('onset_threshold', 'Anschlagschwelle', 'float', .5, 0, 1),
            PluginParameter('frame_threshold', 'Halteschwelle', 'float', .3, 0, 1),
            PluginParameter('minimum_note_length', 'Mindestdauer (ms)', 'int', 127, 20, 2000),
            PluginParameter('minimum_pitch', 'Tiefster MIDI-Ton', 'int', 45, 21, 108),
            PluginParameter('maximum_pitch', 'Höchster MIDI-Ton', 'int', 84, 21, 108),
            PluginParameter('melody_mode', 'Überlappende Noten', 'choice', 'strongest',
                            choices=(('Stärkste Note behalten', 'strongest'), ('Alle behalten', 'all'))),
        ))


def validate_options(options):
    plugin = create_plugin()
    result = {}
    for parameter in plugin.parameters:
        value = options.get(parameter.key, parameter.default)
        if parameter.kind == 'choice':
            if value not in [v for _, v in parameter.choices]:
                raise ValueError(f'Invalid {parameter.key}')
        elif isinstance(value, bool) or not isinstance(value, (float, int)) or not parameter.minimum <= value <= parameter.maximum:
            raise ValueError(f'Invalid {parameter.key}')
        elif parameter.kind == 'int' and not isinstance(value, int):
            raise ValueError(f'{parameter.key} must be an integer')
        result[parameter.key] = value
    if result['minimum_pitch'] > result['maximum_pitch']:
        raise ValueError('Minimum pitch exceeds maximum pitch')
    return result


def project_from_events(events, source, melody_mode='strongest'):
    """Choose the strongest concurrent event, not an unverified vocal separator."""
    import heapq
    import math
    if len(events) > 100000:
        raise ValueError('Too many predicted events')
    clean = []
    for event in events:
        start, end, pitch, strength = event[:4]
        if not all(math.isfinite(float(v)) for v in (start, end, pitch, strength)):
            raise ValueError('Non-finite predicted note')
        if start < 0 or end <= start or int(pitch) != pitch or not 0 <= pitch <= 127:
            raise ValueError('Invalid predicted note')
        clean.append((float(start), float(end), int(pitch), float(strength)))
    notes = []
    if melody_mode == 'all':
        notes = [EditorNote(s, e - s, p) for s, e, p, _ in sorted(clean)]
    elif melody_mode == 'strongest':
        boundaries = {}
        for index, (start, end, _, _) in enumerate(clean):
            boundaries.setdefault(start, []).append((True, index))
            boundaries.setdefault(end, []).append((False, index))
        active, heap = set(), []
        times = sorted(boundaries)
        for index, start in enumerate(times[:-1]):
            for entering, ident in boundaries[start]:
                if entering:
                    active.add(ident)
                    heapq.heappush(heap, (-clean[ident][3], ident))
                else:
                    active.discard(ident)
            while heap and heap[0][1] not in active:
                heapq.heappop(heap)
            if heap:
                pitch = clean[heap[0][1]][2]
                end = times[index + 1]
                if notes and notes[-1].pitch == pitch and abs(notes[-1].time + notes[-1].length - start) < 1e-8:
                    notes[-1].length = end - notes[-1].time
                else:
                    notes.append(EditorNote(start, end - start, pitch))
    else:
        raise ValueError('Invalid melody mode')
    # Fixed editor grid only: transcription times are absolute seconds, not inferred beats.
    project = StudioProject(title=Path(source).stem, notes=notes, audio_path=str(Path(source).resolve()),
                            source='Basic Pitch / Spotify', warnings=[
                                'Automatic pitch draft: review notes, timing and phrase boundaries.',
                                'Lyrics and tempo are not inferred. The editor grid defaults to 120 BPM.',
                                'Basic Pitch does not isolate vocals from a full mix.'])
    project.validate()
    return project
