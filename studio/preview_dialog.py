"""Project-owned preview window shared by audio and video export."""
from PySide6.QtWidgets import (QDialog, QFormLayout, QCheckBox,
                              QDoubleSpinBox, QDialogButtonBox)
from studio.i18n import tr


class PreviewDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('preview.settings'))
        layout = QFormLayout(self)
        self.automatic = QCheckBox(tr('preview.auto'))
        self.automatic.setChecked(project.preview_start is None)
        layout.addRow(self.automatic)
        self.start = QDoubleSpinBox()
        self.start.setRange(0, 86400)
        self.start.setDecimals(3)
        self.start.setSuffix(' s')
        from studio.dlc_media import preview_start_time
        try:
            self.start.setValue(preview_start_time(project))
        except ValueError:
            self.start.setValue(0)
        self.start.setEnabled(not self.automatic.isChecked())
        self.automatic.toggled.connect(lambda checked: self.start.setEnabled(not checked))
        layout.addRow(tr('preview.start'), self.start)
        self.length = QDoubleSpinBox()
        self.length.setRange(0.001, 3600)
        self.length.setDecimals(3)
        self.length.setSuffix(' s')
        self.length.setValue(project.preview_length)
        layout.addRow(tr('preview.length'), self.length)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return (None if self.automatic.isChecked() else self.start.value(), self.length.value())
