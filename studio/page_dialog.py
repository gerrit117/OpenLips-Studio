"""Explicit opt-in lyric-page limits."""
from PySide6.QtWidgets import QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QDialogButtonBox
from studio.i18n import tr
from studio.lyric_pages import DEFAULT_MAX_CHARS, DEFAULT_MAX_NOTES, DEFAULT_MAX_SECONDS


class PageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('pages.title'))
        form = QFormLayout(self)
        self.chars = QSpinBox()
        self.chars.setRange(10, 200)
        self.chars.setValue(DEFAULT_MAX_CHARS)
        form.addRow(tr('pages.chars'), self.chars)
        self.notes = QSpinBox()
        self.notes.setRange(2, 100)
        self.notes.setValue(DEFAULT_MAX_NOTES)
        form.addRow(tr('pages.notes'), self.notes)
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(1, 60)
        self.seconds.setValue(DEFAULT_MAX_SECONDS)
        self.seconds.setSuffix(' s')
        form.addRow(tr('pages.seconds'), self.seconds)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
