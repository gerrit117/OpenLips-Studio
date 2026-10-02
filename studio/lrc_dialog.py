"""Review supplied lyric anchors before attaching them to a Studio project."""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget,
                              QTableWidgetItem, QDialogButtonBox, QHeaderView)
from studio.i18n import tr


class LrcDialog(QDialog):
    def __init__(self, document, parent=None, *, importing=True):
        super().__init__(parent)
        self.setWindowTitle(tr('lrc.title'))
        self.resize(700, 460)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr('lrc.summary', count=len(document.cues), offset=document.offset_ms)))
        table = QTableWidget(len(document.cues), 3)
        table.setHorizontalHeaderLabels([tr('lrc.time'), tr('Songtext'), tr('lrc.words')])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 85)
        table.setColumnWidth(2, 240)
        for row, cue in enumerate(document.cues):
            for column, value in enumerate((f'{cue.time:.3f}', cue.text,
                    '\n'.join(f'{word.time:.3f}: {word.text}' for word in cue.words))):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                table.setItem(row, column, item)
        table.resizeRowsToContents()
        layout.addWidget(table)
        if document.warnings:
            warning = QLabel('\n'.join(document.warnings))
            warning.setWordWrap(True)
            layout.addWidget(warning)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel if importing
                                   else QDialogButtonBox.StandardButton.Close)
        if importing:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('lrc.accept'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
