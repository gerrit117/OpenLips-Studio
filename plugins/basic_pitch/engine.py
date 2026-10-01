"""Basic Pitch's independent note draft and option validation, without Studio imports."""
from pathlib import Path
from dataclasses import asdict, dataclass, field
import uuid


@dataclass
class EditorNote:
    time: float
    length: float
    pitch: int
    text: str = ''
    end_word: bool = True
    line_break_after: bool = False
    id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class StudioProject:
    title: str
    notes: list
    audio_path: str
    source: str
    warnings: list

    def to_payload(self):
        return dict(format='openlips-studio-project', schema_version=1, **asdict(self))


def validate_options(options):
    result = {}
    definitions = [('onset_threshold', .5, 0, 1, float), ('frame_threshold', .3, 0, 1, float),
                   ('minimum_note_length', 127, 20, 2000, int), ('minimum_pitch', 45, 21, 108, int),
                   ('maximum_pitch', 84, 21, 108, int)]
    for key, default, minimum, maximum, kind in definitions:
        value = options.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not minimum <= value <= maximum:
            raise ValueError(f'Invalid {key}')
        if kind is int and not isinstance(value, int):
            raise ValueError(f'{key} must be an integer')
        result[key] = value
    result['melody_mode'] = options.get('melody_mode', 'strongest')
    if result['melody_mode'] not in ('strongest', 'all'):
        raise ValueError('Invalid melody_mode')
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
    return project
