"""Versioned importer contract. Installed plugins are opt-in trusted Python code."""
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Callable

API_VERSION = 1
ENTRY_POINT_GROUP = 'openlips_studio.importers'


@dataclass(frozen=True)
class ImportPlugin:
    id: str
    label: str
    extensions: tuple[str, ...]
    import_file: Callable
    api_version: int = API_VERSION


def discover_plugins(enabled_ids=()):
    plugins, errors = [], []
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        if entry.name not in enabled_ids:
            continue
        try:
            plugin = entry.load()()
            if not isinstance(plugin, ImportPlugin) or plugin.api_version != API_VERSION:
                raise ValueError('incompatible importer API')
            plugins.append(plugin)
        except Exception as error:
            errors.append(f'{entry.name}: {error}')
    return plugins, errors
