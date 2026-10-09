"""Locate incomplete chart notes without guessing from an export error string."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QDialogButtonBox, QHeaderView
import qtawesome as qta

from studio.i18n import tr
from studio.model import incomplete_notes, pitch_name


class ChartReviewDialog(QDialog):
    def __init__(self, projects, parent=None, *, require_text=True, require_pitch=True):
        super().__init__(parent)
        self.projects = projects
        self.chosen = None
        self.setWindowTitle(tr('chart.incomplete'))
        self.resize(720, 400)
        layout = QVBoxLayout(self)
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        self.table.setHeaderLabels([tr('Titel'), tr('chart.note'), tr('Start'), tr('Tonname'), tr('chart.problem')])
        for index, project in enumerate(projects):
            for number, note, reasons in incomplete_notes(project, require_text=require_text, require_pitch=require_pitch):
                time = f'{int(note.time//60):02d}:{note.time%60:06.3f}'
                item = QTreeWidgetItem([f'{project.artist} - {project.title}' if project.artist else project.title,
                    str(number), time, pitch_name(note.pitch) if note.pitch_assigned else '-',
                    ', '.join(tr('chart.'+reason) for reason in reasons)])
                item.setData(0, Qt.ItemDataRole.UserRole, index)
                item.setData(1, Qt.ItemDataRole.UserRole, note.id)
                item.setToolTip(0, item.text(0))
                item.setToolTip(4, item.text(4))
                self.table.addTopLevelItem(item)
        for column in range(4):
            self.table.resizeColumnToContents(column)
        self.table.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        if self.table.topLevelItemCount():
            self.table.setCurrentItem(self.table.topLevelItem(0))
        self.table.itemDoubleClicked.connect(lambda *_: self.accept())
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        jump = buttons.button(QDialogButtonBox.StandardButton.Ok)
        jump.setText(tr('chart.go_note'))
        jump.setIcon(qta.icon('fa5s.crosshairs', color='#cdd3d9'))
        jump.setEnabled(bool(self.table.topLevelItemCount()))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Abbrechen'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        item = self.table.currentItem()
        if item:
            self.chosen = (self.projects[item.data(0, Qt.ItemDataRole.UserRole)],
                           item.data(1, Qt.ItemDataRole.UserRole))
            super().accept()
