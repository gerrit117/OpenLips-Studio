"""Reviewable monophonic analysis data, independent of Qt and inference libraries."""
from __future__ import annotations

from dataclasses import dataclass
import math

from studio.model import EditorNote


@dataclass(frozen=True)
class PitchSpan:
    start: float
    end: float
    pitch: int

    def validate(self):
        if not all(math.isfinite(v) for v in (self.start, self.end)) or not 0 <= self.start < self.end:
            raise ValueError('Invalid pitch span')
        if isinstance(self.pitch, bool) or not isinstance(self.pitch, int) or not 0 <= self.pitch <= 127:
            raise ValueError('Invalid MIDI pitch')


@dataclass(frozen=True)
class WordSpan:
    start: float
    end: float
    text: str
    phrase_end: bool = False
    confidence: float | None = None

    def validate(self):
        if not all(math.isfinite(v) for v in (self.start, self.end)) or not 0 <= self.start < self.end:
            raise ValueError('Invalid word span')
        if not isinstance(self.text, str) or not self.text.strip() or '\x00' in self.text:
            raise ValueError('Invalid recognized word')
        if self.confidence is not None and (not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
            raise ValueError('Invalid word confidence')


def notes_from_analysis(pitches, words=(), minimum_length=.04, word_notes=False):
    """Intersect supplied word windows with measured pitch spans.

    A word across several notes appears once, followed by empty continuation
    notes. This is word timing, NOT phonetic syllabification/forced alignment.
    Non-overlapping pitch outside words remains editable, with no invented text.
    """
    if not math.isfinite(minimum_length) or minimum_length <= 0:
        raise ValueError('Minimum length must be positive')
    pitches, words = list(pitches), list(words)
    if len(pitches) > 100000 or len(words) > 100000:
        raise ValueError('Analysis exceeds note/word safety limit')
    for span in pitches + words:
        span.validate()
    pitches.sort(key=lambda p: p.start)
    words.sort(key=lambda w: w.start)
    for sequence in (pitches, words):
        if any(a.end > b.start + 1e-6 for a, b in zip(sequence, sequence[1:])):
            raise ValueError('Overlapping analysis spans require review')
    notes, warnings, covered = [], [], set()
    grouped_notes = {}
    cursor = 0
    for pitch in pitches:
        while cursor < len(words) and words[cursor].end <= pitch.start:
            cursor += 1
        boundaries = {pitch.start, pitch.end}
        candidates = []
        for index in range(cursor, len(words)):
            word = words[index]
            if word.start >= pitch.end:
                break
            candidates.append((index, word))
            boundaries.update((max(pitch.start, word.start), min(pitch.end, word.end)))
        points = sorted(boundaries)
        for start, end in zip(points, points[1:]):
            if end - start < minimum_length:
                continue
            owner = next(((i, w) for i, w in candidates if w.start <= start + 1e-6 and end <= w.end + 1e-6), None)
            note = EditorNote(start, end - start, pitch.pitch, end_word=False if owner else True)
            if owner:
                index, word = owner
                note.text = word.text.strip() if index not in covered else ''
                covered.add(index)
                grouped_notes.setdefault(index, []).append(note)
            notes.append(note)
    for index, group in grouped_notes.items():
        group[-1].end_word = True
        group[-1].line_break_after = words[index].phrase_end
        if words[index].confidence is not None and words[index].confidence < .6:
            warnings.append(f'Low-confidence word at {words[index].start:.3f}s: {words[index].text.strip()}')
    for index, word in enumerate(words):
        if index not in covered:
            warnings.append(f'No usable pitch for word at {word.start:.3f}s: {word.text.strip()}')
    if word_notes and words:
        from collections import defaultdict
        simplified = []
        for index, group in sorted(grouped_notes.items()):
            durations = defaultdict(float)
            for note in group:
                durations[note.pitch] += note.length
            simplified.append(EditorNote(group[0].time,
                group[-1].time + group[-1].length - group[0].time,
                max(durations, key=durations.get), words[index].text.strip(),
                end_word=True, line_break_after=words[index].phrase_end))
        notes = simplified
        warnings.append('One note per word: dominant measured pitch; melismas simplified, not syllable-aligned.')
    if words:
        warnings.append('Word-level alignment only; sung syllables and page changes need review.')
    else:
        warnings.append('Pitch-only result: lyrics have not been assigned.')
    return notes, warnings


def words_from_lrc(document, audio_end):
    """Use original anchors. Plain lines stay whole; never fake individual words."""
    words, warnings = [], []
    for index, cue in enumerate(document.cues):
        end = document.cues[index + 1].time if index + 1 < len(document.cues) else audio_end
        anchors = cue.words or [cue]
        if not cue.words:
            warnings.append(f'LRC line at {cue.time:.3f}s has no word anchors; retained as one fragment.')
        for position, anchor in enumerate(anchors):
            stop = anchors[position + 1].time if position + 1 < len(anchors) else end
            stop = min(stop, audio_end)
            if anchor.time < 0 or stop <= anchor.time or not anchor.text.strip():
                warnings.append(f'Unusable LRC anchor at {anchor.time:.3f}s')
                continue
            words.append(WordSpan(anchor.time, stop, anchor.text,
                                  phrase_end=position == len(anchors) - 1))
    return words, warnings


def word_error_rate(reference, hypothesis):
    """Case/punctuation-insensitive WER for PRIVATE benchmark reports."""
    import re
    tokenize = lambda text: re.findall(r"[^\W_]+(?:['\u2019][^\W_]+)*", text.casefold())
    expected, actual = tokenize(reference), tokenize(hypothesis)
    if not expected:
        raise ValueError('WER requires reference words')
    if len(expected) > 10000 or len(actual) > 10000:
        raise ValueError('WER input too long')
    row = list(range(len(actual) + 1))
    for i, word in enumerate(expected, 1):
        current = [i]
        for j, candidate in enumerate(actual, 1):
            current.append(min(current[-1] + 1, row[j] + 1, row[j - 1] + (word != candidate)))
        row = current
    return dict(reference_words=len(expected), hypothesis_words=len(actual),
                edit_distance=row[-1], wer=row[-1] / len(expected))
