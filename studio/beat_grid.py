"""Musical editing grid; never changes reference audio or invents word timing."""
import copy
import math
import uuid


def step(project):
    return 60 / project.bpm / project.beat_division


def snap(project, seconds):
    spacing = step(project)
    return max(0, project.beat_offset + round((seconds - project.beat_offset) / spacing) * spacing)


def points(project, start, end, limit=2000):
    spacing = step(project)
    first = math.ceil((start - project.beat_offset) / spacing - 1e-9)
    last = math.floor((end - project.beat_offset) / spacing + 1e-9)
    if last - first + 1 > limit:
        raise ValueError('Beat grid exceeds the editing limit')
    return [(i, project.beat_offset + i * spacing) for i in range(first, last + 1)]


def cut_notes(project, identifiers):
    selected = set(identifiers)
    result = []
    count = 0
    for note in project.ordered():
        cuts = [t for _, t in points(project, note.time, note.time + note.length)
                if note.time + .02 < t < note.time + note.length - .02] if note.id in selected else []
        if not cuts:
            result.append(note)
            continue
        boundaries = [note.time, *cuts, note.time + note.length]
        for i, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
            part = copy.deepcopy(note)
            part.time, part.length = start, end - start
            if i:
                part.id = uuid.uuid4().hex
                part.text = '~'
            if i < len(boundaries) - 2:
                part.end_word = False
                part.line_break_after = False
                part.page_break_time = None
            result.append(part)
        count += len(cuts)
    if len(result) > 100000:
        raise ValueError('Grid cuts exceed the note limit')
    project.notes = result
    return count


def melisma_selection(project, identifiers, text=None, validate_only=False):
    ordered = project.ordered()
    selected = set(identifiers)
    indices = [i for i, note in enumerate(ordered) if note.id in selected]
    if len(indices) < 2 or len(indices) != len(selected) or indices != list(range(indices[0], indices[-1] + 1)):
        raise ValueError('Select consecutive notes for one word')
    notes = [ordered[i] for i in indices]
    if any(n.line_break_after for n in notes[:-1]):
        raise ValueError('A melisma cannot cross lyric pages')
    if indices[0] and not ordered[indices[0] - 1].end_word:
        raise ValueError('Select the beginning of the existing word too')
    if not notes[-1].end_word:
        raise ValueError('Select the ending of the existing word too')
    if validate_only:
        return notes
    if text is None:
        text = ' '.join(dict.fromkeys(n.text.strip() for n in notes if n.text.strip() and n.text.strip() != '~'))
    if not isinstance(text, str) or not text.strip() or '\x00' in text:
        raise ValueError('A melisma needs a word')
    for i, note in enumerate(notes):
        note.text = text.strip() if i == 0 else '~'
        note.end_word = i == len(notes) - 1
    return notes[0]


def trim_overlaps(project, identifiers):
    ordered = project.ordered()
    selected = set(identifiers)
    changes = []
    for note, following in zip(ordered, ordered[1:]):
        if note.id in selected and note.time + note.length > following.time:
            if following.time - note.time < .02:
                raise ValueError('Simultaneous voices need manual selection, not automatic trimming')
            changes.append((note, following.time - note.time))
    for note, length in changes:
        note.length = length
    return len(changes)


def quantize_notes(project, identifiers):
    selected = set(identifiers)
    for note in project.notes:
        if note.id in selected:
            end = snap(project, note.time + note.length)
            note.time = snap(project, note.time)
            note.length = max(step(project), end - note.time)


class BeatClock:
    def __init__(self):
        self.previous = None
        self.signature = None

    def reset(self):
        self.previous = None

    def tick(self, project, position):
        signature = (project.bpm, project.beat_offset, project.beat_division)
        index = math.floor((position - project.beat_offset) / step(project) + 1e-9)
        sound = (project.beat_enabled and project.beat_ticks and self.signature == signature and
                 self.previous is not None and index > self.previous)
        self.previous, self.signature = index, signature
        return (96 if index % project.beat_division == 0 else 91) if sound else None


def detect_beats(audio, rate, initial_bpm=120):
    import numpy as np
    import librosa
    tempo, beats = librosa.beat.beat_track(y=np.asarray(audio, dtype=np.float32), sr=rate,
        start_bpm=initial_bpm, units='time', trim=True)
    bpm = float(np.asarray(tempo).reshape(-1)[0])
    if not math.isfinite(bpm) or not 20 <= bpm <= 400 or len(beats) < 4:
        raise ValueError('No reliable beat sequence found; enter BPM manually')
    # Tempo bins are coarse; fit the observed beat times to reduce accumulated drift.
    spacing, origin = np.polyfit(np.arange(len(beats)), beats, 1)
    refined = 60 / spacing if spacing > 0 else bpm
    if math.isfinite(refined) and abs(refined / bpm - 1) < .05:
        bpm = refined
        offset = float(origin)
    else:
        offset = float(beats[0])
    return round(bpm, 2), offset, len(beats)
