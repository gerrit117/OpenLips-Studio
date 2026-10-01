"""Small original API example, not a song or game asset."""
from studio.model import StudioProject, EditorNote
from studio.plugins import ImportPlugin


def import_file(path):
    return StudioProject(title=path.stem, notes=[EditorNote(0, 1, 60)])


def create_plugin():
    return ImportPlugin('example-importer', 'Example importer', ('.txt',), import_file,
                        description='Minimal original importer example.', author='OpenLips')
