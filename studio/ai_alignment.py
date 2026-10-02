"""Pure token mapping for constrained, explicitly optional lyric alignment."""
import re


def alignment_tokens(text, labels):
    dictionary = {label.lower(): index for index, label in enumerate(labels)}
    tokens, groups, warnings = [], [], []
    for word in re.findall(r'\S+', text):
        chars = []
        ignored = []
        for char in word.lower():
            if char in dictionary and char not in ('-', '|'):
                chars.append(dictionary[char])
            elif char.isalnum():
                ignored.append(char)
        if ignored or not chars:
            raise ValueError(f'Alignment model cannot represent word {word!r}; edit text or use supplied word anchors')
        if tokens and '|' in dictionary:
            tokens.append(dictionary['|'])
        start = len(tokens)
        tokens.extend(chars)
        groups.append((word, start, len(tokens)))
    if not groups or len(tokens) > 2000:
        raise ValueError('Alignment window needs 1..2000 supported characters')
    return tokens, groups, warnings
