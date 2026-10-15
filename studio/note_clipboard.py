"""Versioned, media-free note passages for the system clipboard."""
import copy
from dataclasses import asdict
import json
import math
import uuid
from studio.model import EditorNote

MIME = 'application/x-openlips-notes-v1'
LIMIT = 16 * 1024 * 1024


def capture(project, identifiers):
    ordered = project.ordered()
    requested = set(identifiers)
    selected, group = set(), []
    for index, note in enumerate(ordered):
        group.append(index)
        if note.end_word or note.line_break_after or index == len(ordered) - 1:
            if any(ordered[i].id in requested for i in group):
                selected.update(group)
            group = []
    if not selected:
        return None, set()
    notes = [copy.deepcopy(ordered[i]) for i in sorted(selected)]
    origin = notes[0].time
    ids = {n.id for n in notes}
    for note in notes:
        note.time -= origin
        if note.page_break_time is not None:
            note.page_break_time -= origin
    # A switch to the source's next phrase has no target in the copied passage.
    notes[-1].page_break_time = None
    payload = json.dumps({'version': 1, 'notes': [asdict(n) for n in notes]},
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(payload) > LIMIT:
        raise ValueError('Copied notes exceed the clipboard size limit')
    return payload, ids


def materialize(payload, position, existing_count=0):
    if not math.isfinite(position) or position < 0:
        raise ValueError('Invalid paste position')
    if len(payload) > LIMIT:
        raise ValueError('Clipboard data exceeds the size limit')
    try:
        data = json.loads(bytes(payload).decode('utf-8'))
        if not isinstance(data, dict) or data.get('version') != 1:
            raise ValueError('Unsupported note clipboard format')
        rows = data.get('notes')
        if not isinstance(rows, list) or not rows or len(rows) + existing_count > 100000:
            raise ValueError('Invalid clipboard note count')
        notes = [EditorNote(**row) for row in rows]
        for note in notes:
            if not math.isfinite(note.time) or note.time < 0:
                raise ValueError('Invalid relative note time')
            note.time += position
            if note.page_break_time is not None:
                note.page_break_time = max(0, note.page_break_time + position)
            note.id = uuid.uuid4().hex
            note.validate()
        return notes
    except (TypeError, AttributeError, UnicodeError, OverflowError, RecursionError) as error:
        raise ValueError('Invalid note clipboard data') from error
