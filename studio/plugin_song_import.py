"""Validate and adopt a plugin song bundle without retaining temporary media paths."""
import json
from pathlib import Path
import shutil
import tempfile
import uuid

from studio.plugin_process import relative_path

MAX_ASSET_BYTES = 8 * 1024 * 1024 * 1024


class SongImport:
    def __init__(self, job):
        self.job = Path(job).resolve(strict=True)
        descriptor = self.job / 'result.json'
        descriptor.resolve(strict=True).relative_to(self.job)
        if descriptor.stat().st_size > 65536:
            raise ValueError('Song-import descriptor exceeds 64 KiB')
        data = json.loads(descriptor.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('format') != 'openlips-plugin-song' or data.get('schema_version') != 1:
            raise ValueError('Unsupported song-import result')
        self.paths = {}
        total = 0
        for field in ('chart', 'audio', 'video', 'cover'):
            value = data.get(field)
            if value is None and field != 'chart':
                continue
            relative_path(value)
            path = (self.job / value).resolve(strict=True)
            path.relative_to(self.job)
            if not path.is_file():
                raise ValueError('Song assets must be files')
            total += path.stat().st_size
            self.paths[field] = path
        if total > MAX_ASSET_BYTES:
            raise ValueError('Song assets exceed 8 GiB')
        if self.paths['chart'].suffix.lower() != '.txt' or self.paths['chart'].stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Expected an UltraStar TXT up to 16 MiB')
        self.project = self._project(self.paths)
        from studio.media_reference import reference_video
        self.video_reference = reference_video(data.get('video_reference', '')) or self.project.video_reference
        self.project.video_reference = self.video_reference

    @staticmethod
    def _project(paths):
        from studio.importers import import_ultrastar
        project = import_ultrastar(paths['chart'])
        project.audio_path = str(paths['audio']) if 'audio' in paths else ''
        project.video_path = str(paths['video']) if 'video' in paths else ''
        project.cover_path = str(paths['cover']) if 'cover' in paths else ''
        project.source = 'Plugin song import / UltraStar TXT'
        project.validate()
        return project

    def adopt(self, root):
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = root / uuid.uuid4().hex
        with tempfile.TemporaryDirectory(prefix='.import-', dir=root) as temporary:
            staging = Path(temporary) / 'song'
            staging.mkdir()
            names = {}
            for field, source in self.paths.items():
                source.resolve(strict=True).relative_to(self.job)
                name = field + source.suffix.lower()
                shutil.copy2(source, staging / name)
                names[field] = name
            # Parse the copied TXT before publishing to catch an invalidated source.
            self._project({k: staging / v for k, v in names.items()})
            staging.rename(target)
        project = self._project({k: target / v for k, v in names.items()})
        project.video_reference = self.video_reference
        return project
