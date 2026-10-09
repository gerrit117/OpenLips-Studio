"""Major/minor pitch-class guides; no claim to infer a vocal melody."""
import re

ROOTS = ('C', 'C#', 'Db', 'D', 'D#', 'Eb', 'E', 'F', 'F#', 'Gb',
         'G', 'G#', 'Ab', 'A', 'A#', 'Bb', 'B')
NATURAL = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11, 'H': 11}
MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)


def key_info(value):
    value = value.strip().replace('\u266f', '#').replace('\u266d', 'b')
    match = re.fullmatch(r'([A-GH])([#b]?)(?:\s*(maj(?:or)?|min(?:or)?|dur|moll|m))?',
                         value, re.IGNORECASE)
    if not match:
        return None
    letter, accidental, mode = match.groups()
    root = NATURAL[letter.upper()] + (1 if accidental == '#' else -1 if accidental else 0)
    minor = (mode or '').lower() in ('m', 'min', 'minor', 'moll')
    name = ('B' if letter.upper() == 'H' else letter.upper()) + accidental.lower()
    return dict(root=root % 12, minor=minor, name=name, value=name + ('m' if minor else ''))


def key_pitches(value):
    info = key_info(value)
    return frozenset((info['root'] + interval) % 12 for interval in
                     (MINOR if info['minor'] else MAJOR)) if info else frozenset()
