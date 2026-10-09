"""Render Qt workflow/menu states, not a substitute for native Computer Use."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from unittest.mock import patch
import PySide6.QtCore as QtCore
from PySide6.QtWidgets import QApplication, QMenu
from PySide6.QtTest import QTest

root = Path(__file__).resolve().parents[1] / 'artifacts/menu-review'
root.mkdir(parents=True, exist_ok=True)
NativeSettings = QtCore.QSettings
class QSettings(NativeSettings):
    def __init__(self, *args, **kwargs):
        if len(args) == 2 and all(isinstance(a, str) for a in args):
            super().__init__(str(root/'preferences.ini'), NativeSettings.Format.IniFormat)
        else:
            super().__init__(*args, **kwargs)
QtCore.QSettings = QSettings
from studio.app import StudioWindow
from studio.i18n import set_language
from studio.model import StudioProject, EditorNote
from studio.library_page import LibraryPage
from studio.song_wizard import SongWizard
from studio.usb_dialog import UsbDialog
from studio.usb_catalog import UsbPackage
app = QApplication([])
from studio.fonts import use_system_font
use_system_font(app)
app.setStyle('Fusion')
app.setStyleSheet('QWidget { background: #25292e; color: #e6e9ec; font-size: 13px; } QMenu::item:selected { background: #3c5559; }')
for language in ('de','en'):
    set_language(language, persist=False)
    window = StudioWindow()
    window.resize(1260,790)
    window.show()
    QTest.qWait(100)
    window.grab().save(str(root/f'{language}-welcome.png'))
    for index, menu in enumerate(window.findChildren(QMenu)):
        if not menu.actions():
            continue
        menu.ensurePolished()
        menu.resize(menu.sizeHint())
        menu.grab().save(str(root/f'{language}-menu-{index}.png'))
    project = StudioProject(title='Synthetic',artist='OpenLips',notes=[EditorNote(1,.5,60,'Hello')])
    window.replace_project(project)
    for width,height in ((1260,790),(840,600)):
        window.resize(width,height)
        QTest.qWait(80)
        window.grab().save(str(root/f'{language}-editor-{width}.png'))
    page = LibraryPage(lambda: project, root=root/'library')
    page.library.add_project(project)
    page.library.add_project(StudioProject(title='Unfinished example', artist='OpenLips'))
    page.refresh()
    page.resize(1100,650)
    page.show()
    QTest.qWait(80)
    page.grab().save(str(root/f'{language}-library.png'))
    page.close()
    wizard = SongWizard(window)
    wizard.show()
    for index, mode in enumerate(wizard.modes):
        wizard.choices.setCurrentRow(index)
        QTest.qWait(40)
        wizard.grab().save(str(root/f'{language}-wizard-{mode}.png'))
    wizard.reject()
    with patch('studio.usb_dialog.xbox_volumes', return_value=[]):
        usb = UsbDialog(window, browse=True)
        usb.show_contents([UsbPackage(root/'ABC','Synthetic pack', [dict(artist='OpenLips',title='Hello')],
            '2026-10-09T10:00:00+00:00','utc','abc',0,(1024,0,0,''),local='newer',revision='older')])
        usb.contents.expandAll()
        usb.show()
        QTest.qWait(80)
        usb.grab().save(str(root/f'{language}-usb.png'))
        usb.reject()
    window.dirty = False
    window.close()
    app.processEvents()
print(root)
