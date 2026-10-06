"""Read local UltraStar collections without modifying their source folders."""
from pathlib import Path

from studio.importers import import_ultrastar

MAX_BATCH = 1000
AUDIO = {'.mp3', '.m4a', '.aac', '.wav', '.flac', '.ogg', '.opus', '.wma'}
VIDEO = {'.mp4', '.mkv', '.webm', '.avi', '.wmv', '.mov', '.m4v'}
IMAGES = {'.jpg', '.jpeg', '.png', '.webp'}


def discover_charts(folder):
    root = Path(folder).resolve(strict=True)
    result = []
    for path in root.rglob('*'):
        if path.is_file() and path.suffix.lower() == '.txt':
            try:
                path.resolve(strict=True).relative_to(root)
            except ValueError:
                continue
            result.append(path)
            if len(result) > MAX_BATCH:
                raise ValueError(f'Import at most {MAX_BATCH} TXT files at a time')
    return sorted(result)


def load_chart(path):
    path = Path(path).resolve(strict=True)
    if path.suffix.lower() != '.txt' or path.stat().st_size > 16 * 1024 ** 2:
        raise ValueError('Expected an UltraStar TXT up to 16 MiB')
    project = import_ultrastar(path)
    files = []
    for file in path.parent.iterdir():
        if file.is_file():
            try:
                file.resolve(strict=True).relative_to(path.parent)
            except ValueError:
                continue
            files.append(file)
    for field, extensions in [('audio_path', AUDIO), ('video_path', VIDEO)]:
        if not getattr(project, field):
            matches = [file for file in files if file.suffix.lower() in extensions]
            named = [file for file in matches if file.stem.casefold() == path.stem.casefold()]
            choice = named if len(named) == 1 else matches
            if len(choice) == 1:
                setattr(project, field, str(choice[0]))
    if not project.cover_path:
        images = [file for file in files if file.suffix.lower() in IMAGES]
        covers = [file for file in images if '[co]' in file.stem.lower() or
                  'cover' in file.stem.lower() or file.stem.lower() in ('jacket', 'folder')]
        choice = covers if len(covers) == 1 else images
        if len(choice) == 1:
            project.cover_path = str(choice[0])
    project.validate()
    if not project.notes:
        raise ValueError('TXT contains no notes')
    from studio.page_policy import prepare_pages
    return prepare_pages(project)
