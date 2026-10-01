"""Portable project state. No Qt, platform APIs or template files here."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

FORMAT = "openlips-studio-project"
SCHEMA_VERSION = 1


@dataclass
class EditorNote:
    time: float
    length: float
    pitch: int
    text: str = ""
    end_word: bool = True
    line_break_after: bool = False
    page_break_time: float | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def validate(self):
        if not math.isfinite(self.time) or self.time < 0:
            raise ValueError("Note time must be finite and nonnegative")
        if not math.isfinite(self.length) or self.length <= 0:
            raise ValueError("Note length must be finite and positive")
        if isinstance(self.pitch, bool) or not isinstance(self.pitch, int) or not 0 <= self.pitch <= 127:
            raise ValueError("MIDI pitch must be an integer in 0..127")
        if not isinstance(self.text, str) or '\x00' in self.text:
            raise ValueError("Lyric fragments must be text without embedded NUL")
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("Note ID must be a nonempty string")
        if not isinstance(self.end_word, bool) or not isinstance(self.line_break_after, bool):
            raise ValueError("Word/phrase flags must be boolean")
        if self.page_break_time is not None and (not math.isfinite(self.page_break_time) or self.page_break_time < 0):
            raise ValueError('Page switch time must be finite and nonnegative')


@dataclass
class StudioProject:
    title: str = "Neuer Song"
    artist: str = ""
    bpm: float = 120.0
    key_signature: str = ""
    notes: list[EditorNote] = field(default_factory=list)
    audio_path: str = ""
    video_path: str = ""
    reference_offset: float = 0.0
    source: str = ""
    draft_lyrics: str = ""
    warnings: list[str] = field(default_factory=list)

    def validate(self):
        if not math.isfinite(self.bpm) or not 1 <= self.bpm <= 1000:
            raise ValueError("BPM must be in 1..1000")
        if not math.isfinite(self.reference_offset) or abs(self.reference_offset) > 86400:
            raise ValueError('Invalid reference offset')
        for name in ('title', 'artist', 'key_signature', 'audio_path', 'video_path', 'source', 'draft_lyrics'):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"Project {name} must be text")
        if len(self.notes) > 100000:
            raise ValueError("Project contains too many notes")
        ids = set()
        for note in self.notes:
            note.validate()
            if note.id in ids:
                raise ValueError("Duplicate note ID")
            ids.add(note.id)

    def ordered(self):
        return sorted(self.notes, key=lambda n: n.time)

    @property
    def duration(self):
        return max((n.time + n.length for n in self.notes), default=0.0)

    def lyric_text(self):
        return ''.join(n.text + ('\n' if n.line_break_after else ' ' if n.end_word else '')
                       for n in self.ordered()).rstrip()

    def to_payload(self):
        self.validate()
        return dict(format=FORMAT, schema_version=SCHEMA_VERSION, **asdict(self))

    @classmethod
    def from_payload(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Project must be a JSON object')
        if data.get('format') != FORMAT or data.get('schema_version') != SCHEMA_VERSION:
            raise ValueError("Unsupported OpenLips Studio project version")
        if not isinstance(data.get('notes'), list):
            raise ValueError("Project notes must be a list")
        allowed = set(cls.__dataclass_fields__)
        values = {k: v for k, v in data.items() if k in allowed}
        try:
            values['notes'] = [EditorNote(**n) for n in data['notes']]
            project = cls(**values)
            project.validate()
        except (TypeError, AttributeError) as exc:
            raise ValueError("Invalid project fields") from exc
        return project


def save_project(project, path):
    path = Path(path).resolve()
    data = project.to_payload()
    for field in ('audio_path', 'video_path'):
        if not getattr(project, field):
            continue
        audio = Path(getattr(project, field)).resolve()
        try:
            data[field] = os.path.relpath(audio, path.parent)
        except ValueError:
            data[field] = str(audio)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', suffix='.tmp',
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def load_project(path):
    path = Path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Project exceeds the 64 MiB safety limit")
    project = StudioProject.from_payload(json.loads(path.read_text(encoding='utf-8')))
    for field in ('audio_path', 'video_path'):
        value = getattr(project, field)
        if value and not Path(value).is_absolute():
            setattr(project, field, str((path.parent / value).resolve()))
    return project


def pitch_name(pitch):
    return f"{('C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B')[pitch % 12]}{pitch // 12 - 1}"


def snap_time(seconds, bpm, division=4):
    step = 60.0 / bpm / division
    return max(0.0, round(seconds / step) * step)


def assign_lyrics(project, text, start_index=0, syllabify=False):
    """Explicit spaces separate words; | or soft hyphens separate syllables.

    Never invent phonetic syllables. Newlines create phrase boundaries.
    Return assigned/remaining counts so mismatches are visible to the caller.
    """
    import re
    if start_index < 0:
        raise ValueError('Start index must be nonnegative')
    fragments = []
    for line in text.splitlines():
        line_fragments = []
        for word in line.split():
            pieces = re.split(r'[|\u00ad]', word) if syllabify else [word]
            pieces = [p for p in pieces if p]
            for i, piece in enumerate(pieces):
                line_fragments.append((piece, i == len(pieces) - 1, False))
        if line_fragments:
            last = line_fragments[-1]
            line_fragments[-1] = (last[0], last[1], True)
        fragments.extend(line_fragments)
    notes = project.ordered()[start_index:]
    for note, (fragment, end_word, phrase) in zip(notes, fragments):
        note.text, note.end_word, note.line_break_after = fragment, end_word, phrase
    return min(len(notes), len(fragments)), max(0, len(fragments) - len(notes))


def suggest_syllables(text, language='en_US'):
    """Optional dictionary hyphenation, not verified phonetic sung syllables."""
    import re
    import pyphen
    dictionary = pyphen.Pyphen(lang=language)
    return re.sub(r'(?u)\b[^\W\d_]+\b', lambda match: dictionary.inserted(match.group(), hyphen='|'), text)


def demo_project():
    project = StudioProject(title="First Light", artist="OpenLips Studio", bpm=108,
                            key_signature="C", source="Synthetic demo")
    phrases = [('Sing', 'a', 'new', 'song', 'with', 'me'),
               ('Let', 'the', 'melody', 'lead', 'the', 'way'),
               ('Every', 'word', 'finds', 'a', 'place', 'here')]
    for row, words in enumerate(phrases):
        for i, word in enumerate(words):
            project.notes.append(EditorNote(row * 8 + 1 + i * .9, .65 if i < 5 else 1.2,
                                            [60, 62, 64, 67, 65, 64][i] + (2 if row == 1 else 0),
                                            word, line_break_after=i == 5))
    return project
