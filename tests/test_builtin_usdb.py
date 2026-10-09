"""Built-in USDB routes do not depend on a registered plugin or its GUI."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys

from PySide6.QtWidgets import QApplication
from studio.model import StudioProject
from studio.song_wizard import SongWizard
from studio.usdb import backend


def test_builtin_command_uses_headless_service(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    executable=tmp_path/'usdb/OpenLipsUSDB'/('OpenLipsUSDB.exe' if os.name=='nt' else 'OpenLipsUSDB')
    executable.parent.mkdir(parents=True)
    executable.touch()
    service=backend()
    command=service.create_command(tmp_path/'unused.json',tmp_path/'output')
    assert service.id=='studio-usdb'
    assert command==[str(executable),'--serve','--output',str(tmp_path/'output')]
    assert '--request' not in command


def test_wizard_imports_usdb_without_intermediate_project_or_plugin(monkeypatch):
    app=QApplication.instance() or QApplication([])
    project=StudioProject(title='USDB demo',artist='Test')
    class AcceptedSignal:
        def connect(self, callback):
            pass
    class Browser:
        accepted_song=AcceptedSignal()
        batch_result=([project],'Demo',False)
        def exec(self):
            return True
    monkeypatch.setattr('studio.usdb.dialog',lambda *args:Browser())
    wizard=SongWizard()
    wizard.restart()
    wizard.choices.setCurrentRow(wizard.modes.index('usdb'))
    assert not wizard.usdb_start.isHidden()
    wizard.open_usdb()
    assert wizard.project is project and wizard.usdb_result[0]==[project]
    app.processEvents()
