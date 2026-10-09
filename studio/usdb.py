"""Built-in native USDB workflow; no Syncer application window or plugin setup."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace


def backend():
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    name = 'OpenLipsUSDB.exe' if os.name == 'nt' else 'OpenLipsUSDB'
    candidates = [root / 'usdb/OpenLipsUSDB' / name]
    if not getattr(sys, 'frozen', False):
        candidates += [root / 'private/runtime/workers/OpenLipsUSDB' / name]
    executable = next((path for path in candidates if path.is_file()), None)
    if not executable:
        from studio.i18n import tr
        raise ValueError(tr('usdb.backend_missing'))
    def command(request, output, python_override=''):
        return [str(executable), '--serve', '--output', str(output)]
    return SimpleNamespace(id='studio-usdb', label='USDB', create_command=command)


def dialog(project, parent=None):
    from studio.plugin_download_dialog import PluginDownloadDialog
    return PluginDownloadDialog(backend(), 'usdb-browser', project, parent)
