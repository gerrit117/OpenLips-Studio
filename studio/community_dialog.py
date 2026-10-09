"""Media-free community export; project saving remains a separate action."""
from PySide6.QtWidgets import (QDialog, QFormLayout, QLineEdit, QDoubleSpinBox,
                               QCheckBox, QPushButton, QFileDialog, QMessageBox)
from studio.i18n import tr
from studio.exporters import export_community_song, community_duration, community_reference


class CommunityExportDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.setWindowTitle(tr('export.community'))
        self.resize(560, 320)
        layout = QFormLayout(self)
        self.fields = {}
        for key, label in (('album', 'export.album'), ('genre', 'export.genre'),
                           ('language', 'export.language'), ('youtube', 'export.reference')):
            control = QLineEdit()
            if key in ('album', 'genre'):
                control.setText(getattr(project, key))
            self.fields[key] = control
            if key == 'youtube':
                control.setText(community_reference(project))
                control.setPlaceholderText('https://www.youtube.com/watch?v=...')
            layout.addRow(tr(label), control)
        self.duration = QDoubleSpinBox()
        self.duration.setDecimals(3)
        self.duration.setRange(.001, 1800)
        self.duration.setValue(community_duration(project))
        layout.addRow(tr('export.duration'), self.duration)
        self.rights = QCheckBox(tr('export.rights'))
        layout.addRow(self.rights)
        self.save_button = QPushButton(tr('export.save'))
        self.save_button.clicked.connect(self.save)
        layout.addRow(self.save_button)

    def save(self):
        if not self.rights.isChecked():
            QMessageBox.warning(self, 'OpenLips Studio', tr('export.need_rights'))
            return
        path, _ = QFileDialog.getSaveFileName(self, tr('export.save'),
                                             self.project.title + '.ols', 'OpenLips Song (*.ols)')
        if not path:
            return
        if not path.lower().endswith('.ols'):
            path += '.ols'
        try:
            export_community_song(self.project, path, duration=self.duration.value(),
                                  **{key: field.text().strip() for key, field in self.fields.items()})
        except Exception as error:
            QMessageBox.critical(self, 'OpenLips Studio', str(error))
            return
        self.accept()
