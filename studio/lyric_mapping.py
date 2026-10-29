"""Occurrence-aware lyric anchors; note times and pitches are never changed."""
import re


def note_words(notes):
    groups = []
    for note in notes:
        previous = groups[-1]['notes'][-1] if groups else None
        continuation = previous and (note.text.strip() == '~' or
            (previous.text.strip() and not previous.end_word and not previous.line_break_after))
        if continuation:
            groups[-1]['notes'].append(note)
        else:
            groups.append(dict(notes=[note]))
    return groups


def tokens(text):
    return [(match.start(), match.end(), match.group()) for match in re.finditer(r'\S+', text)]


def normalized(text):
    return ''.join(c for c in text.casefold() if c.isalnum())


def lyric_links(project):
    text = project.draft_lyrics or project.lyric_text()
    words = tokens(text)
    units = note_words(project.ordered())
    valid_spans = {(a, b) for a, b, _ in words}
    links, used = {}, set()
    for unit in units:
        anchor = unit['notes'][0]
        explicit = project.lyric_assignments.get(anchor.id)
        if explicit and tuple(explicit) in valid_spans:
            a, b = explicit
            if normalized(text[a:b]) == normalized(''.join(n.text.replace('~', '') for n in unit['notes'])):
                links[anchor.id] = (a, b)
                used.add((a, b))
    cursor = 0
    for unit in units:
        anchor = unit['notes'][0]
        if anchor.id in links:
            continue
        fragment = normalized(''.join(n.text.replace('~', '') for n in unit['notes']))
        if not fragment:
            continue
        for index in range(cursor, len(words)):
            a, b, word = words[index]
            if (a, b) not in used and normalized(word) == fragment:
                links[anchor.id] = (a, b)
                used.add((a, b))
                cursor = index + 1
                break
    return links


def assign_word(project, start, end, identifiers):
    text = project.draft_lyrics or project.lyric_text()
    if (start, end) not in {(a, b) for a, b, _ in tokens(text)}:
        raise ValueError('Select one complete lyric word')
    ordered = project.ordered()
    chosen = [n for n in ordered if n.id in set(identifiers)]
    if not chosen:
        raise ValueError('Select a note first')
    positions = [ordered.index(n) for n in chosen]
    if positions != list(range(positions[0], positions[-1]+1)):
        raise ValueError('Select consecutive notes for a word')
    units = note_words(ordered)
    if len(chosen) == 1:
        chosen = next(unit['notes'] for unit in units if chosen[0] in unit['notes'])
    if any(n.line_break_after for n in chosen[:-1]):
        raise ValueError('A word cannot cross a page boundary')
    links = lyric_links(project)
    source = next((unit['notes'] for unit in units if links.get(unit['notes'][0].id) == (start, end)), None)
    replacement = ''.join(n.text.replace('~', '') for n in chosen)
    old_link = links.get(chosen[0].id)
    if source and not {n.id for n in source}.issubset({n.id for n in chosen}):
        if {n.id for n in source} & {n.id for n in chosen}:
            raise ValueError('Overlapping lyric groups')
        source[0].text = replacement
        for n in source[1:]:
            n.text = '~'
        if old_link:
            project.lyric_assignments[source[0].id] = list(old_link)
        else:
            project.lyric_assignments.pop(source[0].id, None)
    project.draft_lyrics = text
    chosen[0].text = text[start:end].replace('|', '')
    for index, note in enumerate(chosen):
        if index:
            note.text = '~'
        note.end_word = index == len(chosen)-1
        project.lyric_assignments.pop(note.id, None)
    project.lyric_assignments[chosen[0].id] = [start, end]
    project.validate()
    return chosen[0].id
