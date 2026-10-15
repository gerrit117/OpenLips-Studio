"""Loss-aware passage, lyric and conflict operations independent of Qt."""
import copy


def lyric_slots(project):
    slots, group = [], []
    for note in project.ordered():
        group.append(note)
        if note.end_word or note.line_break_after:
            slots.append(group)
            group = []
    if group:
        slots.append(group)
    return slots


def lyric_shift_plan(project, identifier, direction, suffix=False):
    slots = lyric_slots(project)
    index = next((i for i,g in enumerate(slots) if any(n.id == identifier for n in g)), -1)
    if direction not in (-1, 1) or index < 0 or not 0 <= index + direction < len(slots):
        raise ValueError('lyrics.no_slot')
    values = [[n.text for n in group] for group in slots]
    if suffix:
        boundary = len(slots)-1 if direction == 1 else index-1
        if any(text.replace('~','').strip() for text in values[boundary]):
            raise ValueError('lyrics.no_room')
        if direction == 1:
            values[index:] = [['']] + values[index:-1]
        else:
            values[index-1:] = values[index:] + [['']]
        indices = range(index if direction == 1 else index-1,len(slots))
    else:
        values[index],values[index+direction] = values[index+direction],values[index]
        indices = [index,index+direction]
    plan = []
    for i in indices:
        group, fragments = slots[i], values[i]
        if len(group) != len(fragments):
            fragments = [''.join(t.replace('~','') for t in fragments)] + ['~']*(len(group)-1)
        for j,note in enumerate(group):
            plan.append((note, fragments[j], j == len(group)-1))
    return plan


def conflicts(project, limit=4000):
    active, result, pairs = [], {}, 0
    for note in project.ordered():
        active = [n for n in active if n.time+n.length > note.time+1e-6]
        for other in active:
            same = (abs(note.time-other.time)<1e-6 and abs(note.length-other.length)<1e-6
                    and note.pitch == other.pitch)
            reason = 'duplicate' if same else 'overlap'
            for item in (note,other):
                result.setdefault(item.id,set()).add(reason)
            pairs += 1
            if pairs >= limit:
                return result
        active.append(note)
    return result


def duplicate_ids(project):
    kept, removed = {}, set()
    for note in project.ordered():
        key = (round(note.time,6),round(note.length,6),note.pitch,note.pitch_assigned)
        candidates = kept.setdefault(key,[])
        match = next((n for n in candidates if n.text == note.text or not n.text.strip() or not note.text.strip()),None)
        if match is None:
            candidates.append(note)
        elif not match.text.strip() and note.text.strip():
            removed.add(match.id)
            candidates.remove(match)
            candidates.append(note)
        else:
            removed.add(note.id)
    return removed


def passage_destination(project, notes, mode):
    if mode not in ('replace','add'):
        raise ValueError('Invalid insertion mode')
    candidate = copy.deepcopy(project)
    if mode == 'replace':
        from studio.lyric_timing import delete_notes
        start,end = min(n.time for n in notes),max(n.time+n.length for n in notes)
        identifiers = {n.id for n in candidate.notes if n.time < end-1e-6 and n.time+n.length > start+1e-6}
        delete_notes(candidate,identifiers)
    candidate.notes.extend(notes)
    candidate.validate()
    return candidate.notes
