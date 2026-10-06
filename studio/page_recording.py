"""Record explicit page timing without retiming notes or splitting words."""
from dataclasses import dataclass
import math

from studio.smart_pages import word_units


@dataclass(frozen=True)
class PageSwitch:
    note_id: str
    time: float
    requested_time: float

    @property
    def adjusted(self):
        return abs(self.time - self.requested_time) > .001


def plan_page_switch(project, seconds):
    """Choose the nearest complete-word boundary; preserve a gap's exact time."""
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError('Page switch time must be finite and nonnegative')
    units = word_units(project.ordered())
    if len(units) < 2 or seconds < units[0]['start'] or seconds >= units[-1]['end']:
        return None
    candidates = []
    for previous, following in zip(units, units[1:]):
        low, high = previous['end'], following['start']
        if low > high + 1e-6:
            continue
        effective = min(high, max(low, seconds))
        candidates.append((abs(effective - seconds), effective, previous['notes'][-1].id))
    if not candidates:
        return None
    _, effective, identifier = min(candidates)
    return PageSwitch(identifier, effective, seconds)


def apply_page_switch(project, switch):
    note = next(n for n in project.notes if n.id == switch.note_id)
    if note.line_break_after and note.page_break_time == switch.time and project.page_layout_mode == 'manual':
        return False
    note.line_break_after = True
    note.page_break_time = switch.time
    project.page_layout_mode = 'manual'
    return True


def clear_page_switches(project):
    changed = False
    for note in project.notes:
        changed |= note.line_break_after or note.page_break_time is not None
        note.line_break_after = False
        note.page_break_time = None
    if changed:
        project.page_layout_mode = 'manual'
    return changed
