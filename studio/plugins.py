"""Versioned importer contract and opt-in discovery; no GUI or ML imports here."""
from __future__ import annotations

from dataclasses import dataclass
import importlib.util
from importlib.metadata import entry_points
import json
from pathlib import Path
import re
import sys
from typing import Callable

API_VERSION = 1
ENTRY_POINT_GROUP = 'openlips_studio.importers'


@dataclass(frozen=True)
class PluginParameter:
    key: str
    label: str
    kind: str
    default: object
    minimum: float = 0
    maximum: float = 1
    choices: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True)
class ImportPlugin:
    id: str
    label: str
    extensions: tuple[str, ...]
    import_file: Callable | None
    api_version: int = API_VERSION
    description: str = ''
    author: str = ''
    version: str = '1.0'
    homepage: str = ''
    parameters: tuple[PluginParameter, ...] = ()
    create_command: Callable | None = None
    process_plugin: bool = False
    permissions: tuple[str, ...] = ()
    result_type: str = 'note-draft'
    input_required: bool = True
    interactive: bool = False
    ui_actions: tuple[dict, ...] = ()

    def validate(self):
        if self.api_version != API_VERSION:
            raise ValueError('incompatible importer API')
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', self.id):
            raise ValueError('invalid plugin ID')
        if not self.label or not (callable(self.import_file) or callable(self.create_command)):
            raise ValueError('plugin needs a label and importer or process runner')
        if self.parameters and not callable(self.create_command):
            raise ValueError('parameterized plugins require a process runner')
        keys = set()
        for parameter in self.parameters:
            if parameter.key in keys or parameter.kind not in ('float', 'int', 'bool', 'choice', 'text'):
                raise ValueError('invalid or duplicate plugin parameter')
            keys.add(parameter.key)


@dataclass(frozen=True)
class PluginOffer:
    id: str
    label: str
    source: str
    load: Callable


def load_local_plugin(manifest):
    """Called only after explicit trust/enablement. Plugins have full user access."""
    manifest = Path(manifest).resolve()
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('api_version') == 2:
        from studio.plugin_process import load_process_plugin
        return load_process_plugin(manifest.parent, data)
    source = (manifest.parent / data['module']).resolve()
    source.relative_to(manifest.parent)
    if source.suffix != '.py' or not source.is_file():
        raise ValueError('plugin module must be a Python file inside its folder')
    module_name = '_openlips_plugin_' + re.sub(r'[^a-zA-Z0-9_]', '_', data['id'])
    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return getattr(module, data.get('factory', 'create_plugin'))()
    except Exception:
        sys.modules.pop(module_name, None)
        raise


def available_plugins(folders=()):
    offers = []
    errors = []
    seen = set()
    for entry in entry_points(group=ENTRY_POINT_GROUP):
        if entry.name in seen:
            errors.append(f'{entry.name}: duplicate plugin ID')
            continue
        seen.add(entry.name)
        offers.append(PluginOffer(entry.name, entry.name, 'Installed package', lambda ep=entry: ep.load()()))
    for folder in folders:
        try:
            manifest = Path(folder) / 'openlips-plugin.json'
            if manifest.stat().st_size > 64 * 1024:
                raise ValueError('manifest exceeds 64 KiB')
            data = json.loads(manifest.read_text(encoding='utf-8'))
            if data.get('api_version') == 2:
                from studio.plugin_process import validate_manifest
                validate_manifest(data)
            ident = data['id']
            if not isinstance(ident, str) or not re.fullmatch(r'[a-zA-Z0-9_.-]+', ident):
                raise ValueError('invalid plugin ID')
            if ident in seen:
                raise ValueError('duplicate plugin ID')
            seen.add(ident)
            offers.append(PluginOffer(ident, data.get('label', ident), str(manifest.parent),
                                      lambda path=manifest: load_local_plugin(path)))
        except Exception as error:
            errors.append(f'{folder}: {error}')
    return offers, errors


def discover_plugins(enabled_ids=(), folders=()):
    plugins, errors = [], []
    offers, discovery_errors = available_plugins(folders)
    errors.extend(discovery_errors)
    for entry in offers:
        if entry.id not in enabled_ids:
            continue
        try:
            plugin = entry.load()
            if not isinstance(plugin, ImportPlugin):
                raise ValueError('incompatible importer API')
            plugin.validate()
            if plugin.id != entry.id:
                raise ValueError('plugin ID differs from registered ID')
            plugins.append(plugin)
        except Exception as error:
            errors.append(f'{entry.id}: {error}')
    return plugins, errors
