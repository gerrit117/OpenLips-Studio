"""Dependency-free protocol example, not an automatic syllable alignment model."""
import argparse
import copy
import json
from pathlib import Path
import sys


def run(request, output):
    if request.get('protocol') != 1:
        raise ValueError('Unsupported request protocol')
    project = copy.deepcopy(request['project'])
    if project.get('format') != 'openlips-studio-project' or not project.get('notes'):
        raise ValueError('Create or import notes before mapping words')
    source = Path(request['input'])
    if source.stat().st_size > 1024 * 1024:
        raise ValueError('Example text input exceeds 1 MiB')
    words = source.read_text(encoding='utf-8-sig').split()
    overwrite = request.get('options', {}).get('overwrite', False)
    targets = [n for n in sorted(project['notes'], key=lambda n: n['time']) if overwrite or not n.get('text')]
    if not words or not targets:
        raise ValueError('No words or eligible notes')
    for note, word in zip(targets, words):
        note['text'] = word
        note['end_word'] = True
    project['warnings'] = ['Example mapping only: review syllable boundaries and timing.']
    if len(words) != len(targets):
        project['warnings'].append(f'{len(words)} words for {len(targets)} eligible notes; unmatched items remain unchanged.')
    project['source'] = 'Example lyric mapping'
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'result.json').write_text(json.dumps(project, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print('OPENLIPS_PLUGIN:' + json.dumps({'progress': 100, 'message': 'Word draft ready'}), flush=True)
    return project


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.request.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Request too large')
        run(json.loads(args.request.read_text(encoding='utf-8')), args.output)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
