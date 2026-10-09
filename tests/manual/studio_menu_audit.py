"""Launch isolated synthetic Studio data for a manual Computer Use audit."""
from pathlib import Path
import sys
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import PySide6.QtCore as QtCore
from PySide6.QtWidgets import QApplication

root = Path(__file__).resolve().parents[1] / 'artifacts/menu-audit'
root.mkdir(parents=True, exist_ok=True)
NativeSettings = QtCore.QSettings
NativeSettings.setPath(NativeSettings.Format.IniFormat, NativeSettings.Scope.UserScope, str(root/'preferences'))
class QSettings(NativeSettings):
    def __init__(self, *args, **kwargs):
        if len(args) == 2 and all(isinstance(a, str) for a in args):
            super().__init__(NativeSettings.Format.IniFormat, NativeSettings.Scope.UserScope, *args)
        else:
            super().__init__(*args, **kwargs)
QtCore.QSettings = QSettings
from studio.library import Library
from studio.model import StudioProject, EditorNote
from studio.app import StudioWindow
settings = QSettings('OpenLips', 'OpenLips Studio')
settings.setValue('library/enabled', True)
settings.setValue('library/root', str(root/'library'))
settings.setValue('ui/language', 'de')
audio = root/'silent.wav'
with wave.open(str(audio), 'wb') as stream:
    stream.setparams((1,2,44100,0,'NONE','not compressed'))
    stream.writeframes(bytes(44100*2*4))
library = Library(root/'library')
for text in ('', 'Hello'):
    project = StudioProject(title='Synthetic audit', artist='OpenLips', audio_path=str(audio),
        genre='Test', year='1990', notes=[EditorNote(1,.5,60,text)])
    library.add_project(project)
app = QApplication([])
from studio.fonts import use_system_font
use_system_font(app)
window = StudioWindow()
window.resize(1260, 800)
window.show()
raise SystemExit(app.exec())
