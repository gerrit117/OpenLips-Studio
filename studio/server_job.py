"""Isolated main-thread Qt/media worker; only accepts registered project IDs."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from studio.library import Library
from studio.model import load_project


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--job', required=True)
    args = parser.parse_args(argv)
    library = Library(args.library)
    with library.connect() as db:
        row = db.execute('SELECT request FROM jobs WHERE id=? AND state=?', (args.job, 'running')).fetchone()
    if not row:
        raise ValueError('Unknown or inactive job')
    request = json.loads(row['request'])
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance() or QGuiApplication([])

    def report(message):
        # API progress is stage-only, never raw encoder output or local paths.
        with library.connect() as db:
            db.execute('UPDATE jobs SET progress=? WHERE id=?', ('Encoding / packaging', args.job))

    try:
        kind = request.get('kind', 'dlc')
        if kind != 'dlc':
            from studio.library_exchange import chart_artifact
            with tempfile.TemporaryDirectory(prefix='openlips-charts-') as folder:
                artifact = chart_artifact(library, request['projects'][0], folder, kind)
                package_id = library.add_artifact(artifact, kind, request['projects'][0])
            with library.connect() as db:
                db.execute('UPDATE jobs SET state=?,progress=?,package_id=? WHERE id=?',
                    ('ready', 'Chart/lyrics ready', package_id, args.job))
            return 0
        from studio.dlc_pack import build_projects_dlc
        projects = [load_project(library.project_path(identifier)) for identifier in request['projects']]
        with tempfile.TemporaryDirectory(prefix='openlips-server-') as folder:
            result = build_projects_dlc(projects, folder, report, pack_name=request.get('pack_name'), optimize_pages=True)
            package_id = library.add_package(result['output_path'], request['projects'])
            library.record_build(package_id, request['projects'], request.get('pack_name'), True)
        with library.connect() as db:
            db.execute('UPDATE jobs SET state=?,progress=?,package_id=? WHERE id=?',
                       ('ready', 'Ready for transfer', package_id, args.job))
        return 0
    except Exception:
        with library.connect() as db:
            db.execute('UPDATE jobs SET state=?,progress=? WHERE id=?',
                       ('failed', 'Build failed; see local worker log', args.job))
        raise


if __name__ == '__main__':
    raise SystemExit(main())
