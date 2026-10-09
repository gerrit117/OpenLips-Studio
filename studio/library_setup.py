"""One-time folder choice and fixed export locations for the optional library."""
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QFileDialog, QDialogButtonBox

from studio.library import Library, default_library_root
from studio.i18n import tr


def export_directory():
    from studio.library_page import configured_library
    root = configured_library()
    return Library(root).root / 'publish' if root else None


class LibrarySetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('library.directory'))
        self.resize(600, 220)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        settings = QSettings('OpenLips', 'OpenLips Studio')
        self.path = QLineEdit(str(settings.value('library/root', str(default_library_root()))))
        row.addWidget(self.path)
        browse = QPushButton(tr('wizard.browse'))
        browse.clicked.connect(self.browse)
        row.addWidget(browse)
        layout.addLayout(row)
        label = QLabel(tr('library.folder_hint'))
        label.setWordWrap(True)
        layout.addWidget(label)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.store)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, tr('library.directory'), self.path.text())
        if path:
            self.path.setText(path)

    def store(self):
        try:
            if not self.path.text().strip():
                raise ValueError(tr('library.directory'))
            library = Library(Path(self.path.text()).expanduser())
            settings = QSettings('OpenLips', 'OpenLips Studio')
            settings.setValue('library/root', str(library.root))
            settings.setValue('library/enabled', True)
            self.accept()
        except Exception as error:
            self.status.setText(str(error))
