"""Local synchronized lyric anchors, separate from inferred singing notes."""
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import re

LIMIT = 2 * 1024 * 1024
MAX_CUES = 10000
MAX_WORDS = 100000
STAMP = r'(\d{1,4}):([0-5]\d)(?:\.(\d{1,3}))?'
LINE = re.compile(r'\[' + STAMP + r'\]')
WORD = re.compile(r'<' + STAMP + r'>')
META = re.compile(r'^\[([A-Za-z]+):(.*)\]$')


@dataclass
class LyricAnchor:
    time: float
    text: str
    words: list['LyricAnchor'] = field(default_factory=list)


@dataclass
class LrcDocument:
    raw: str
    cues: list[LyricAnchor]
    metadata: dict[str, str]
    offset_ms: int
    warnings: list[str]

    def plain_text(self):
        return '\n'.join(cue.text for cue in self.cues)


def _seconds(match):
    minute, second, fraction = match.groups()
    return Decimal(minute) * 60 + Decimal(second) + Decimal('0.' + (fraction or '0'))


def parse_lrc(text):
    if not isinstance(text, str) or '\x00' in text:
        raise ValueError('LRC must be text without NUL bytes')
    if len(text.encode('utf-8')) > LIMIT:
        raise ValueError('LRC exceeds the 2 MiB limit')
    original = text
    metadata, cues, warnings = {}, [], []
    word_count = 0
    for number, raw in enumerate(text.lstrip('\ufeff').splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        meta = META.fullmatch(line)
        if meta:
            metadata[meta[1].lower()] = meta[2].strip()
            continue
        starts, pos = [], 0
        while match := LINE.match(line, pos):
            starts.append(_seconds(match))
            pos = match.end()
        if not starts:
            warnings.append(f'Line {number}: no supported timestamp; retained in source only')
            continue
        fragment = line[pos:]
        markers = list(WORD.finditer(fragment))
        words = []
        for i, match in enumerate(markers):
            stop = markers[i + 1].start() if i + 1 < len(markers) else len(fragment)
            words.append((_seconds(match), fragment[match.end():stop]))
        visible = WORD.sub('', fragment)
        if '<' in visible and re.search(r'<\d+:', visible):
            raise ValueError(f'Line {number}: invalid enhanced timestamp')
        word_count += len(words) * len(starts)
        if len(cues) + len(starts) > MAX_CUES or word_count > MAX_WORDS:
            raise ValueError('LRC exceeds the lyric anchor limit')
        for start in starts:
            # Repeated line anchors retain the word offsets of the first occurrence.
            shift = start - starts[0]
            cues.append((start, visible, [(time + shift, word) for time, word in words]))
    try:
        offset = int(metadata.get('offset', '0'))
    except ValueError as exc:
        raise ValueError('Invalid LRC offset in milliseconds') from exc
    if abs(offset) > 86400000:
        raise ValueError('LRC offset exceeds one day')
    if not cues:
        raise ValueError('LRC contains no supported synchronized lyric lines')
    adjustment = Decimal(offset) / 1000
    result = []
    for time, text, words in cues:
        # Positive LRC offset advances lyrics; do not reapply on project loading.
        anchor = LyricAnchor(float(time - adjustment), text,
                             [LyricAnchor(float(t - adjustment), w) for t, w in words])
        if any(w.time < anchor.time for w in anchor.words):
            warnings.append('Enhanced word anchor precedes its line')
        if any(b.time < a.time for a, b in zip(anchor.words, anchor.words[1:])):
            warnings.append('Enhanced word anchors are not chronological')
        result.append(anchor)
    result.sort(key=lambda cue: cue.time)
    if any(cue.time < 0 or any(w.time < 0 for w in cue.words) for cue in result):
        warnings.append('LRC offset produces negative anchors; retained without clamping')
    return LrcDocument(original, result, metadata, offset, list(dict.fromkeys(warnings)))


def read_lrc(path):
    path = Path(path)
    if path.stat().st_size > LIMIT:
        raise ValueError('LRC exceeds the 2 MiB limit')
    return parse_lrc(path.read_text(encoding='utf-8-sig'))


def attach_lrc(project, document, source=''):
    """Attach source/anchors only. Never invent notes, pitches or word durations."""
    project.lyric_reference = dict(format='lrc', raw=document.raw, source=str(source))
    project.draft_lyrics = document.plain_text()


def assign_lrc_notes(project, document):
    """Distribute supplied text over existing notes, never alter their music.

    Plain LRC has line times only: distribute words over note onsets within
    each line window as an editable estimate, not claimed forced alignment.
    """
    notes = project.ordered()
    windows = []
    for index, cue in enumerate(document.cues):
        end = document.cues[index + 1].time if index + 1 < len(document.cues) else float('inf')
        anchors = cue.words or [cue]
        for position, anchor in enumerate(anchors):
            stop = anchors[position + 1].time if position + 1 < len(anchors) else end
            if anchor.text.strip() and stop > anchor.time:
                windows.append((anchor.time, stop, anchor.text, position == len(anchors) - 1))
    # LRC line times are often coarser than MIDI onsets. Allow a note that
    # starts just before a lyric anchor but still overlaps it to belong to
    # that line. Choose one owner only; never stretch notes across large gaps.
    owners = {}
    for note in notes:
        candidates = [i for i, (start, end, _, _) in enumerate(windows)
                      if start - min(.2, note.length) <= note.time < end]
        if candidates:
            owners[note.id] = candidates[-1]
    assigned = 0
    for index, (start, end, text, phrase_end) in enumerate(windows):
        group = [note for note in notes if owners.get(note.id) == index]
        words = text.split()
        if not group or not words:
            continue
        for i, note in enumerate(group):
            left = (i * len(words) + len(group) - 1) // len(group)
            right = ((i + 1) * len(words) + len(group) - 1) // len(group)
            note.text = ' '.join(words[left:right]) or '~'
            note.end_word = right > left
            note.line_break_after = False
            note.page_break_time = None
            assigned += 1
        group[-1].end_word = True
        group[-1].line_break_after = phrase_end
    if assigned:
        message = 'LRC text assigned to existing notes as an estimate; review word/syllable placement.'
        if message not in project.warnings:
            project.warnings.append(message)
    return assigned
