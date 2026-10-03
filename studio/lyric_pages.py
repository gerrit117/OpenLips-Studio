"""Optional readability limits, not claimed Xbox font or format constraints."""
import math

DEFAULT_MAX_CHARS = 30
DEFAULT_MAX_NOTES = 8
DEFAULT_MAX_SECONDS = 3.0


def optimize_pages(project, max_chars=DEFAULT_MAX_CHARS, max_notes=DEFAULT_MAX_NOTES,
                   max_seconds=DEFAULT_MAX_SECONDS):
    if not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError('Character limit must be positive')
    if not isinstance(max_notes, int) or max_notes < 1:
        raise ValueError('Note limit must be positive')
    if not math.isfinite(max_seconds) or max_seconds <= 0:
        raise ValueError('Page duration must be finite and positive')
    project.validate()
    notes = project.ordered()
    units, current, ended = [], [], False
    for i, note in enumerate(notes):
        current.append(note)
        ended = ended or note.end_word
        next_text = i + 1 < len(notes) and bool(notes[i + 1].text.replace('~', '').strip())
        if note.line_break_after or (ended and next_text) or i == len(notes) - 1:
            units.append(current)
            current, ended = [], False
    page, chars, added, oversized = [], 0, 0, 0
    for unit in units:
        text = ''.join(n.text.replace('~', '') for n in unit).strip()
        new_chars = chars + (1 if page else 0) + len(text)
        new_notes = len(page) + len(unit)
        duration = max(n.time + n.length for n in page + unit) - (page or unit)[0].time
        if page and (new_chars > max_chars or new_notes > max_notes or duration > max_seconds):
            page[-1].line_break_after = True
            page[-1].page_break_time = None
            added += 1
            page, chars = [], 0
        unit_duration = max(n.time + n.length for n in unit) - unit[0].time
        if len(text) > max_chars or len(unit) > max_notes or unit_duration > max_seconds:
            oversized += 1  # A whole word/melisma is indivisible; report, never truncate.
        chars += (1 if page else 0) + len(text)
        page.extend(unit)
        if unit[-1].line_break_after:
            page, chars = [], 0
    return dict(added_breaks=added, oversized_words=oversized,
                pages=sum(n.line_break_after for n in notes[:-1]) + bool(notes))
