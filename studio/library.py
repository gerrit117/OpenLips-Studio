"""Opt-in, persistent project/media/package storage, independent of Qt."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager

from studio import __version__
from studio.model import load_project, save_project
from studio.package_metadata import package_metadata
from tools.build_dlc import marketplace_filename, verify_stfs


def default_library_root():
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
    else:
        base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    return base / 'OpenLips' / 'Library'


class Library:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ('projects', 'media', 'publish', '.staging', 'workspace'):
            path = self.root / name
            if path.is_symlink():
                raise ValueError('Library directories must not be symbolic links')
            path.mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL, artist TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS packages (
                    id TEXT PRIMARY KEY, filename TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
                    bytes INTEGER NOT NULL, songs TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS package_projects (
                    package_id TEXT NOT NULL, project_id TEXT NOT NULL,
                    PRIMARY KEY(package_id,project_id));
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, request TEXT NOT NULL, state TEXT NOT NULL,
                    progress TEXT NOT NULL, package_id TEXT, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS build_cache (
                    recipe TEXT PRIMARY KEY, package_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, filename TEXT UNIQUE NOT NULL,
                    kind TEXT NOT NULL, project_id TEXT NOT NULL, bytes INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS project_types (project_id TEXT PRIMARY KEY, kind TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sync_links (
                    server_id TEXT NOT NULL, kind TEXT NOT NULL, local_id TEXT NOT NULL,
                    remote_id TEXT NOT NULL, PRIMARY KEY(server_id,kind,local_id,remote_id));
            ''')

    def draft_path(self, project):
        import re
        label = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',
                       f'{project.artist} - {project.title}').strip(' .-')[:100] or 'Song'
        return self.root / 'workspace' / (label + '-' + uuid.uuid4().hex[:12] + '.olp')

    def sync_links(self, server_id, kind):
        with self.connect() as db:
            return [(row['local_id'], row['remote_id']) for row in db.execute(
                'SELECT local_id,remote_id FROM sync_links WHERE server_id=? AND kind=?', (server_id, kind))]

    def link_remote(self, server_id, kind, local_id, remote_id):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO sync_links VALUES (?,?,?,?)',
                       (server_id, kind, local_id, remote_id))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'library.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def store_file(self, source, category, filename=None, progress=lambda message: None, validator=None):
        source = Path(source).resolve(strict=True)
        if not source.is_file():
            raise ValueError('Library source must be a regular file')
        directory = self.root / category
        progress(str(source.name))
        if category == 'media' and source.parent == directory and filename is None:
            from tools.build_dlc import sha256
            checksum = sha256(source)
            if source.stem != checksum:
                raise ValueError('Managed media changed outside the library')
            return source, checksum
        temporary = None
        try:
            with source.open('rb') as src, tempfile.NamedTemporaryFile(dir=self.root / '.staging', delete=False) as dst:
                temporary = Path(dst.name)
                digest = hashlib.sha256()
                for chunk in iter(lambda: src.read(1024 * 1024), b''):
                    digest.update(chunk)
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            checksum = digest.hexdigest()
            if validator:
                validator(temporary, checksum)
            suffix = source.suffix.lower()
            suffix = suffix if len(suffix) <= 16 and suffix.isascii() else '.dat'
            target = directory / (filename or (checksum + suffix))
            if target.parent != directory or target.is_symlink():
                raise ValueError('Invalid managed library path')
            try:
                os.link(temporary, target)
            except FileExistsError:
                from tools.build_dlc import sha256
                if sha256(target) != checksum:
                    raise ValueError('Library file conflicts with existing content')
            return target, checksum
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def add_project(self, project, progress=lambda message: None):
        project = copy.deepcopy(project)
        project.validate()
        if project.video_path and not project.audio_path:
            from studio.dlc_media import bundled_tool, resolve_audio_source
            probe = bundled_tool('ffprobe')
            if probe:
                audio = resolve_audio_source(project, probe)
                if Path(audio).resolve() != Path(project.video_path).resolve():
                    project.audio_path = audio
        digests = {}
        for field in ('audio_path', 'video_path', 'cover_path'):
            source = getattr(project, field)
            if source:
                target, digest = self.store_file(source, 'media', progress=progress)
                setattr(project, field, str(target))
                digests[field] = digest
        payload = project.to_payload()
        for field in ('audio_path', 'video_path', 'cover_path'):
            payload[field] = digests.get(field, '')
        # Editor UUIDs and import-path labels are not musical identity.
        payload.pop('source', None)
        for note in payload['notes']:
            note.pop('id', None)
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True,
            ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        identifier = uuid.uuid4().hex
        with self.connect() as db:
            existing = db.execute('SELECT id FROM projects WHERE fingerprint=?', (fingerprint,)).fetchone()
            if existing:
                return existing['id']
            save_project(project, self.root / 'projects' / (identifier + '.olp'))
            db.execute('INSERT INTO projects VALUES (?,?,?,?,?)',
                (identifier, fingerprint, project.title, project.artist, time.time()))
            source = project.source.lower()
            kind = ('community' if source in ('openlips song', 'library ols') else
                    'ultrastar' if source in ('ultrastar txt', 'library txt') else
                    'midi' if source.startswith('midi /') or source in ('library mid', 'library midi') else
                    'lrc' if source == 'library lrc' else 'project')
            db.execute('INSERT INTO project_types VALUES (?,?)', (identifier, kind))
        return identifier

    def project_path(self, identifier):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM projects WHERE id=?', (identifier,)).fetchone():
                raise KeyError('Unknown library project')
        return self.root / 'projects' / (identifier + '.olp')

    def add_package(self, path, project_ids=(), progress=lambda message: None):
        verified = verify_stfs(path)
        metadata = package_metadata(path)
        filename = marketplace_filename(path)
        def validate_copy(temporary, checksum):
            if checksum != verified['sha256'] or verify_stfs(temporary)['sha256'] != checksum:
                raise ValueError('Source package changed during archiving')
        target = self.root / 'publish' / filename
        if Path(path).resolve() == target and not Path(path).is_symlink():
            checksum = verified['sha256']
        else:
            target, checksum = self.store_file(path, 'publish', filename, progress, validate_copy)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO packages VALUES (?,?,?,?,?,?)',
                (checksum, filename, metadata['title'], target.stat().st_size,
                 json.dumps(metadata['songs'], ensure_ascii=False), time.time()))
            for identifier in project_ids:
                if not db.execute('SELECT 1 FROM projects WHERE id=?', (identifier,)).fetchone():
                    raise KeyError('Unknown library project')
                db.execute('INSERT OR IGNORE INTO package_projects VALUES (?,?)', (checksum, identifier))
        return checksum

    def projects(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('''SELECT id,title,artist,created,
                COALESCE((SELECT kind FROM project_types t WHERE t.project_id=projects.id), 'project') AS kind,
                (SELECT count(*) FROM package_projects l WHERE l.project_id=projects.id) AS packages
                FROM projects ORDER BY artist COLLATE NOCASE,title COLLATE NOCASE''')]

    def packages(self):
        with self.connect() as db:
            result = [dict(row) for row in db.execute('SELECT * FROM packages ORDER BY title COLLATE NOCASE')]
        for row in result:
            row['songs'] = json.loads(row['songs'])
        return result

    def songs(self):
        records = [dict(key='project:' + p['id'], project_id=p['id'],
                        title=p['title'], artist=p['artist'], kind=p['kind'])
                   for p in self.projects()]
        for package in self.packages():
            for index, song in enumerate(package['songs']):
                records.append(dict(key=f"dlc:{package['id']}:{index}",
                    title=song['title'] or package['title'], artist=song['artist'],
                    kind='dlc', song_id=song['song_id'], package_id=package['id'],
                    package_title=package['title'], filename=package['filename'],
                    bytes=package['bytes'], song_count=len(package['songs'])))
        return sorted(records, key=lambda p: (p['artist'].casefold(), p['title'].casefold(), p['key']))

    def add_artifact(self, path, kind, project_id):
        from tools.build_dlc import sha256
        suffix = {'chart': '.ols', 'midi': '.mid', 'lrc': '.lrc'}[kind]
        self.project_path(project_id)
        identifier = sha256(path)
        target, digest = self.store_file(path, 'publish', identifier + suffix)
        if digest != identifier:
            raise ValueError('Artifact changed during archiving')
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO artifacts VALUES (?,?,?,?,?,?)',
                (identifier, target.name, kind, project_id, target.stat().st_size, time.time()))
        return identifier

    def artifacts(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT * FROM artifacts ORDER BY created DESC')]

    def artifact_path(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT filename FROM artifacts WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise KeyError('Unknown artifact')
        path = self.root / 'publish' / row['filename']
        if path.is_symlink() or path.resolve().parent != self.root / 'publish':
            raise ValueError('Invalid artifact path')
        return path

    def remove_project(self, identifier):
        self.project_path(identifier)
        with self.connect() as db:
            db.execute('DELETE FROM projects WHERE id=?', (identifier,))
            db.execute('DELETE FROM project_types WHERE project_id=?', (identifier,))
            db.execute('DELETE FROM package_projects WHERE project_id=?', (identifier,))
            db.execute('DELETE FROM build_cache')
        (self.root / 'projects' / (identifier + '.olp')).unlink(missing_ok=True)
        # Shared media and previously built packages are retained, never guessed as orphaned.

    def package_path(self, identifier):
        with self.connect() as db:
            row = db.execute('SELECT filename FROM packages WHERE id=?', (identifier,)).fetchone()
        if not row:
            raise KeyError('Unknown library package')
        path = self.root / 'publish' / row['filename']
        if path.is_symlink() or path.resolve().parent != self.root / 'publish':
            raise ValueError('Invalid published package path')
        return path

    def cached_package(self, identifiers, pack_name=None):
        expected = set(identifiers)
        with self.connect() as db:
            for package in db.execute('SELECT id,title FROM packages ORDER BY created DESC').fetchall():
                if pack_name is not None and package['title'] != pack_name:
                    continue
                ids = {r['project_id'] for r in db.execute(
                    'SELECT project_id FROM package_projects WHERE package_id=?', (package['id'],))}
                if ids == expected:
                    path = self.package_path(package['id'])
                    if path.is_file() and verify_stfs(path)['sha256'] == package['id']:
                        return package['id']
        return None

    @staticmethod
    def recipe(identifiers, pack_name, optimize_pages):
        return json.dumps(dict(projects=list(identifiers), pack_name=pack_name,
                               optimize_pages=optimize_pages, studio_version=__version__), sort_keys=True)

    def record_build(self, package_id, identifiers, pack_name=None, optimize_pages=None):
        self.package_path(package_id)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO build_cache VALUES (?,?)',
                       (self.recipe(identifiers, pack_name, optimize_pages), package_id))

    def cached_build(self, identifiers, pack_name=None, optimize_pages=None):
        with self.connect() as db:
            row = db.execute('SELECT package_id FROM build_cache WHERE recipe=?',
                (self.recipe(identifiers, pack_name, optimize_pages),)).fetchone()
        if row:
            path = self.package_path(row['package_id'])
            if path.is_file() and verify_stfs(path)['sha256'] == row['package_id']:
                return row['package_id']
        return None
