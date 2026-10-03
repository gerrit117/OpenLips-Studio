"""Global lyric-page planning, with soft targets from the original-song corpus."""
import math
import re

from studio.lyric_pages import DEFAULT_MAX_CHARS, DEFAULT_MAX_NOTES, DEFAULT_MAX_SECONDS

# Soft linguistic hints, not a grammar parser or hard forbidden boundaries.
LINK_WORDS = frozenset(('a an the of to in on at for with from by and or'
                       ' der die das ein eine einem einen einer eines des den dem'
                       ' und oder mit von zu zum zur im am auf').split())
MAX_PAGE_WORDS = 64


def word_units(notes):
    units, group, ended = [], [], False
    for index, note in enumerate(notes):
        group.append(note)
        ended = ended or note.end_word
        following_text = index + 1 < len(notes) and bool(notes[index + 1].text.replace('~', '').strip())
        if index == len(notes) - 1 or (ended and following_text):
            unit = dict(notes=group, text=''.join(n.text.replace('~', '') for n in group).strip(),
                        start=group[0].time, end=max(n.time + n.length for n in group),
                        shortest=min(n.length for n in group))
            # Overlapping vocal events must not be separated into different pages.
            if units and unit['start'] < units[-1]['end'] - 1e-6:
                previous = units[-1]
                previous['notes'] += group
                previous['text'] += ' ' + unit['text']
                previous['end'] = max(previous['end'], unit['end'])
                previous['shortest'] = min(previous['shortest'], unit['shortest'])
            else:
                units.append(unit)
            group, ended = [], False
    return units


def boundary_cost(unit, following):
    gap = max(0.0, following['start'] - unit['end'])
    text = unit['text'].rstrip('"\')]}')
    cost = 1.0 - .65 * min(2.0, gap / .25)
    if text.endswith(('.', '!', '?', ';', ':')):
        cost -= 1.9
    elif text.endswith(','):
        cost -= .35
    words = re.findall(r'\w+', text.casefold())
    if words and words[-1] in LINK_WORDS:
        cost += 2.2
    if unit['notes'][-1].line_break_after:
        cost -= .65
    return cost


def page_cost(chars, count, span, shortest):
    # Median: 16 chars / 5 notes / 1.447 s; 95th percentiles: 30 / 8 / 2.492 s.
    cost = .8 + .22 * ((chars - 16) / 16) ** 2
    cost += .45 * ((count - 5) / 5) ** 2 + .65 * ((span - 1.447) / 1.447) ** 2
    for value, target, weight in ((chars, DEFAULT_MAX_CHARS, 12),
                                  (count, DEFAULT_MAX_NOTES, 14),
                                  (span, DEFAULT_MAX_SECONDS, 12)):
        cost += weight * max(0.0, value / target - 1) ** 2
    # A visibility proxy only: the native renderer determines actual pixel width.
    fraction = shortest / span if span > 0 else 1
    cost += .35 * max(0.0, (.0673 - fraction) / .0673) ** 2
    return cost


def plan_pages(project):
    """Plan globally over complete word groups; never mutate the project."""
    project.validate()
    notes = project.ordered()
    units = word_units(notes)
    size = len(units)
    scores, next_page = [math.inf] * size + [0.0], [size] * size
    for start in range(size - 1, -1, -1):
        chars = count = 0
        end = units[start]['end']
        shortest = math.inf
        for last in range(start, min(size, start + MAX_PAGE_WORDS)):
            unit = units[last]
            chars += len(unit['text']) + (last > start)
            count += len(unit['notes'])
            end = max(end, unit['end'])
            shortest = min(shortest, unit['shortest'])
            score = page_cost(chars, count, end - units[start]['start'], shortest) + scores[last + 1]
            if last + 1 < size:
                score += boundary_cost(unit, units[last + 1])
            if score < scores[start] - 1e-9:
                scores[start], next_page[start] = score, last + 1
    breaks, oversized = [], 0
    start = 0
    while start < size:
        stop = next_page[start]
        if stop < size:
            breaks.append(units[stop - 1]['notes'][-1].id)
        if stop == start + 1:
            unit = units[start]
            if (len(unit['text']) > DEFAULT_MAX_CHARS or len(unit['notes']) > DEFAULT_MAX_NOTES
                    or unit['end'] - unit['start'] > DEFAULT_MAX_SECONDS):
                oversized += 1
        start = stop
    return dict(break_ids=breaks, pages=len(breaks) + bool(notes), oversized_words=oversized)


def intelligent_pages(project):
    """Explicit reflow; restore old layout/timed switches through editor undo."""
    plan = plan_pages(project)
    chosen = set(plan['break_ids'])
    notes = project.ordered()
    before = {n.id for n in notes[:-1] if n.line_break_after}
    changed = False
    for note in notes[:-1]:
        enabled = note.id in chosen
        changed |= note.line_break_after != enabled or note.page_break_time is not None
        note.line_break_after = enabled
        note.page_break_time = None
    return dict(pages=plan['pages'], added_breaks=len(chosen - before),
                removed_breaks=len(before - chosen), oversized_words=plan['oversized_words'], changed=changed)
