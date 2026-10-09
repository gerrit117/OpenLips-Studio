"""Atomic project/media exchange for a private library, not a community file."""
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from studio.model import StudioProject
from studio.library_exchange import INPUT_LIMIT, validate_media_header

BUNDLE_LIMIT = 7 * 1024 ** 3
EXTENSIONS = {
    'audio': {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma', '.xwma'},
    'video': {'.mp4', '.mkv', '.webm', '.mov', '.avi', '.wmv'},
    'cover': {'.png', '.jpg', '.jpeg', '.webp'},
}


def write_bundle(project, target, progress=lambda message: None):
    payload = project.to_payload()
    for field in ('audio', 'video', 'cover'):
        payload[field + '_path'] = ''
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as archive:
        archive.writestr('project.json', json.dumps(payload, ensure_ascii=False, allow_nan=False))
        for field in ('audio', 'video', 'cover'):
            source = getattr(project, field + '_path')
            if source:
                path = Path(source)
                extension = path.suffix.lower()
                if extension not in EXTENSIONS[field]:
                    raise ValueError(f'Unsupported {field} file: {extension}')
                progress(f'{field}: {path.name}')
                archive.write(path, field + extension)


def import_bundle(library, source):
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        names = [entry.filename for entry in members]
        if not 1 <= len(names) <= 4 or len(set(names)) != len(names) or 'project.json' not in names:
            raise ValueError('Invalid library project bundle')
        fields = {}
        for entry in members:
            if entry.flag_bits & 1 or entry.compress_type != zipfile.ZIP_STORED:
                raise ValueError('Use an unencrypted, uncompressed library bundle')
            if entry.filename == 'project.json':
                limit = INPUT_LIMIT
            else:
                match = re.fullmatch(r'(audio|video|cover)(\.[a-z0-9]+)', entry.filename)
                if not match or match[2] not in EXTENSIONS[match[1]] or match[1] in fields:
                    raise ValueError('Invalid library media filename')
                fields[match[1]] = entry
                limit = 8 * 1024 ** 2 if match[1] == 'cover' else 2 * 1024 ** 3
            if entry.file_size > limit or entry.file_size < 1:
                raise ValueError('Library bundle entry exceeds size limit')
        payload = json.loads(archive.read('project.json'))
        for field in EXTENSIONS:
            payload[field + '_path'] = ''
        project = StudioProject.from_payload(payload)
        with tempfile.TemporaryDirectory(dir=library.root / '.staging') as folder:
            for field, entry in fields.items():
                target = Path(folder) / entry.filename
                with archive.open(entry) as src, target.open('xb') as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                if field == 'cover':
                    from PIL import Image
                    with Image.open(target) as image:
                        if image.width * image.height > 16 * 1024 ** 2 or image.format not in ('PNG', 'JPEG', 'WEBP'):
                            raise ValueError('Unsupported cover')
                        image.verify()
                else:
                    validate_media_header(target, field)
                setattr(project, field + '_path', str(target))
            return library.add_project(project)
