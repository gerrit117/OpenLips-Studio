"""Lyric-first drafts: explicit onsets and unassigned pitches, no vocal inference."""
import copy
from dataclasses import dataclass
import math
from pathlib import Path
import re

from studio.model import EditorNote
from studio.lrc import attach_lrc


@dataclass(frozen=True)
class TextUnit:
    text: str
    end_word: bool = True
    end_line: bool = False


def text_units(text, mode='word'):
    if mode not in ('word', 'syllable') or not isinstance(text, str) or '\x00' in text:
        raise ValueError('Invalid lyric timing text or mode')
    if len(text.encode('utf-8')) > 2 * 1024 * 1024:
        raise ValueError('Lyrics exceed 2 MiB')
    units = []
    for line in text.splitlines():
        words = [w.replace('~','') for w in line.split() if w.replace('~','')]
        for word_index, word in enumerate(words):
            parts = [p for p in word.split('|') if p] if mode == 'syllable' else [word.replace('|', '')]
            for index, part in enumerate(parts):
                if part:
                    units.append(TextUnit(part, index == len(parts)-1,
                        word_index == len(words)-1 and index == len(parts)-1))
        if len(units) > 100000:
            raise ValueError('Lyrics contain too many timing units')
    return units


def timed_draft(project, onsets, text, mode='word', end=None):
    if not onsets:
        raise ValueError('Record at least one onset')
    if len(onsets) > 100000 or any(not math.isfinite(t) or t < 0 for t in onsets):
        raise ValueError('Invalid lyric onsets')
    if any(b-a < .001 for a,b in zip(onsets,onsets[1:])):
        raise ValueError('Lyric onsets must be strictly increasing')
    if end is not None and (not math.isfinite(end) or end <= onsets[-1]):
        raise ValueError('Final lyric end must follow its onset')
    units = text_units(text, mode)
    candidate = copy.deepcopy(project)
    candidate.notes = []
    candidate.draft_lyrics = text
    candidate.page_layout_mode = 'automatic'
    for index, start in enumerate(onsets):
        stop = onsets[index+1] if index+1 < len(onsets) else (end if end is not None else start+2)
        unit = units[index] if index < len(units) else TextUnit('')
        candidate.notes.append(EditorNote(start, stop-start, 60, unit.text,
            unit.end_word, unit.end_line and index+1 < len(onsets), pitch_assigned=False))
    candidate.source = 'Lyric timing draft'
    candidate.validate()
    return candidate


def lrc_draft(project, document, source='', end=None):
    candidate = copy.deepcopy(project)
    attach_lrc(candidate, document, source)
    candidate.notes = []
    candidate.page_layout_mode = 'automatic'
    for index, cue in enumerate(document.cues):
        stop = document.cues[index+1].time if index+1 < len(document.cues) else end
        anchors = cue.words or [cue]
        for number, anchor in enumerate(anchors):
            if not anchor.text.strip():
                continue
            if anchor.time < 0:
                raise ValueError('Negative LRC anchors need an offset correction')
            finish = anchors[number+1].time if number+1 < len(anchors) else stop
            if finish is None:
                finish = anchor.time+2
            if finish <= anchor.time:
                raise ValueError('LRC anchors must be strictly chronological')
            fragment = anchor.text.strip()
            word_end = not cue.words or anchor.text[-1:].isspace() or number == len(anchors)-1
            candidate.notes.append(EditorNote(anchor.time, finish-anchor.time, 60, fragment,
                word_end, False, pitch_assigned=False))
        if candidate.notes:
            candidate.notes[-1].line_break_after = index+1 < len(document.cues) and any(
                c.text.strip() for c in document.cues[index+1:])
    if not candidate.notes:
        raise ValueError('LRC contains no nonempty timed lyrics')
    candidate.source = 'LRC lyric draft'
    candidate.validate()
    return candidate


def split_note(project, identifier, seconds):
    note = next(n for n in project.notes if n.id == identifier)
    if not note.time+.001 <= seconds <= note.time+note.length-.001:
        raise ValueError('Split must fall inside the note')
    right = EditorNote(seconds, note.time+note.length-seconds, note.pitch, '~',
        note.end_word, note.line_break_after, note.page_break_time, pitch_assigned=note.pitch_assigned)
    note.length = seconds-note.time
    note.end_word = note.line_break_after = False
    note.page_break_time = None
    project.notes.append(right)
    return right


def split_words(project, identifier):
    note = next(n for n in project.notes if n.id == identifier)
    words = note.text.split()
    if len(words) < 2 or note.length/len(words) < .001:
        raise ValueError('Select a block with multiple words')
    length = note.length/len(words)
    result = [EditorNote(note.time+i*length,length,note.pitch,word, True,
        note.line_break_after if i == len(words)-1 else False,
        note.page_break_time if i == len(words)-1 else None, pitch_assigned=note.pitch_assigned)
        for i,word in enumerate(words)]
    project.notes[:] = [n for n in project.notes if n.id != identifier]+result
    return result


def stamp(seconds):
    if not math.isfinite(seconds) or not 0 <= seconds < 600000:
        raise ValueError('LRC time is out of range')
    ms = round(seconds*1000)
    if ms >= 600000000:
        raise ValueError('LRC time is out of range')
    return f'{ms//60000:02d}:{ms//1000%60:02d}.{ms%1000:03d}'


def enhanced_lrc(project):
    project.validate()
    notes = project.ordered()
    if not notes or any(not n.text.strip() for n in notes):
        raise ValueError('Every timed lyric block needs text before LRC export')
    if any(b.time<=a.time or b.time<a.time+a.length-.0001 for a,b in zip(notes,notes[1:])):
        raise ValueError('Resolve overlapping lyric blocks before LRC export')
    lines, group = [], []
    for index,note in enumerate(notes):
        group.append(note)
        if note.line_break_after or index == len(notes)-1:
            line = '['+stamp(group[0].time+project.reference_offset)+']'
            for n in group:
                # LRC has no separate onset for the later pitches of a melisma.
                text = n.text.replace('~','')
                if not text.strip():
                    continue
                if '\n' in text or '\r' in text or re.search(r'[<>\[\]]',text):
                    raise ValueError('Lyric text contains reserved LRC characters')
                line += '<'+stamp(n.time+project.reference_offset)+'>'+text+(' ' if n.end_word else '')
            line += '<'+stamp(group[-1].time+group[-1].length+project.reference_offset)+'>'
            lines.append(line)
            group = []
    return '\n'.join(lines)+'\n'


def write_lrc(project, path):
    path = Path(path)
    if path.suffix.lower() != '.lrc':
        raise ValueError('Choose a .lrc filename')
    data = enhanced_lrc(project)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(data)
