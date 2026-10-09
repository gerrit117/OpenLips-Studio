"""Guided song setup; imports finish before replacing the current project."""
from pathlib import Path
from PySide6.QtWidgets import (QWizard, QWizardPage, QVBoxLayout, QHBoxLayout,
    QListWidget, QLabel, QLineEdit, QPushButton, QFormLayout, QWidget, QFileDialog,
    QComboBox, QMessageBox)
from studio.i18n import tr
from studio.model import StudioProject
from studio.importers import import_ultrastar, read_midi, project_from_midi


class SongWizard(QWizard):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('wizard.title'))
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        for button, key in ((QWizard.WizardButton.BackButton,'wizard.back'),
                            (QWizard.WizardButton.NextButton,'wizard.next'),
                            (QWizard.WizardButton.FinishButton,'wizard.finish'),
                            (QWizard.WizardButton.CancelButton,'Abbrechen')):
            self.setButtonText(button,tr(key))
        self.resize(760, 480)
        self.project = None
        self.choice = 'ultrastar'
        self.modes = ['ultrastar', 'midi-lrc', 'midi', 'lrc', 'usdb', 'scratch']
        self.usdb_result = None
        page = QWizardPage()
        page.setTitle(tr('wizard.start'))
        row = QHBoxLayout(page)
        self.choices = QListWidget()
        self.choices.addItems([tr('wizard.only_lrc' if mode == 'lrc' else 'wizard.' + mode) for mode in self.modes])
        self.choices.setFixedWidth(245)
        self.description = QLabel()
        self.description.setWordWrap(True)
        row.addWidget(self.choices)
        detail = QVBoxLayout()
        detail.addWidget(self.description, 1)
        self.lrc_sources = QWidget()
        sources = QHBoxLayout(self.lrc_sources)
        sources.setContentsMargins(0, 0, 0, 0)
        self.own_lrc = QPushButton(tr('wizard.own_lrc'))
        self.find_lrc = QPushButton(tr('wizard.find_lrc'))
        self.own_lrc.clicked.connect(self.choose_lrc_file)
        self.find_lrc.clicked.connect(self.find_lrc_file)
        sources.addWidget(self.own_lrc)
        sources.addWidget(self.find_lrc)
        detail.addWidget(self.lrc_sources)
        self.usdb_start = QPushButton(tr('download.usdb'))
        self.usdb_start.clicked.connect(self.open_usdb)
        detail.addWidget(self.usdb_start)
        row.addLayout(detail, 1)
        self.choices.currentRowChanged.connect(self.choose_mode)
        self.choices.setCurrentRow(0)
        self.addPage(page)
        files = QWizardPage()
        files.setTitle(tr('wizard.files'))
        form = QFormLayout(files)
        self.rows = {}
        for key, label, filters in (
            ('chart', 'wizard.chart', 'UltraStar (*.txt);;MIDI (*.mid *.midi)'),
            ('lrc', 'wizard.lrc', 'LRC (*.lrc)'),
            ('media', 'wizard.media', 'Media (*.mp4 *.mkv *.wmv *.mov *.webm *.mp3 *.wav *.flac *.m4a *.wma *.xWMA);;All files (*)'),
            ('cover', 'Cover laden', 'Images (*.jpg *.jpeg *.png *.webp)')):
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit()
            button = QPushButton(tr('wizard.browse'))
            button.clicked.connect(lambda checked=False, e=edit, f=filters: self.browse(e, f))
            layout.addWidget(edit, 1)
            layout.addWidget(button)
            if key == 'lrc':
                find = QPushButton(tr('wizard.find_lrc'))
                find.clicked.connect(self.find_lrc_file)
                layout.addWidget(find)
            form.addRow(tr(label), widget)
            self.rows[key] = (edit, widget, form.labelForField(widget))
        self.method = QComboBox()
        self.method.addItem(tr('wizard.manual'), 'manual')
        self.method.addItem(tr('timing.title'), 'timing')
        self.method.addItem('Basic Pitch (.opl)', 'plugin')
        self.method.addItem(tr('ai.title'), 'ai')
        form.addRow(tr('wizard.method'), self.method)
        self.method_label = form.labelForField(self.method)
        self.media_kind = QComboBox()
        self.media_kind.addItem(tr('wizard.video'), 'video')
        self.media_kind.addItem(tr('wizard.audio'), 'audio')
        form.addRow(tr('wizard.media_kind'), self.media_kind)
        self.currentIdChanged.connect(self.update_fields)
        self.addPage(files)

    def choose_mode(self, index):
        self.choice = self.modes[index]
        self.description.setText(tr('wizard.' + self.choice + '.description'))
        self.lrc_sources.setVisible(self.choice in ('lrc', 'midi-lrc'))
        self.usdb_start.setVisible(self.choice == 'usdb')

    def open_usdb(self):
        from studio.usdb import dialog
        try:
            browser = dialog(StudioProject(), self)
            browser.accepted_song.connect(lambda project: setattr(self, 'project', project))
            if browser.exec():
                if browser.batch_result:
                    self.usdb_result = browser.batch_result
                    self.project = browser.batch_result[0][0]
                if self.project:
                    self.accept()
        except Exception as error:
            QMessageBox.warning(self, 'OpenLips Studio', str(error))

    def choose_lrc_file(self):
        self.browse(self.rows['lrc'][0], 'LRC (*.lrc)')
        if self.rows['lrc'][0].text() and self.currentId() == 0:
            self.next()

    def find_lrc_file(self):
        from studio.lyrics_lookup_dialog import LyricsLookupDialog
        dialog = LyricsLookupDialog(self)
        if dialog.exec() and dialog.lrc_path:
            self.rows['lrc'][0].setText(str(dialog.lrc_path))
            if self.currentId() == 0:
                self.next()

    def browse(self, field, filters):
        if field is self.rows['chart'][0]:
            filters = 'UltraStar (*.txt)' if self.choice == 'ultrastar' else 'MIDI (*.mid *.midi)'
        path, _ = QFileDialog.getOpenFileName(self, tr('wizard.browse'), '', filters)
        if path:
            field.setText(path)
            if field is self.rows['media'][0]:
                kind = 'audio' if Path(path).suffix.lower() in ('.mp3', '.wav', '.flac', '.m4a', '.wma', '.xwma', '.ogg', '.aac') else 'video'
                self.media_kind.setCurrentIndex(self.media_kind.findData(kind))

    def update_fields(self, index):
        self.rows['chart'][2].setText('UltraStar TXT' if self.choice == 'ultrastar' else 'MIDI')
        for key in ('chart', 'lrc'):
            visible = (key == 'chart' and self.choice in ('ultrastar','midi','midi-lrc')) or (key == 'lrc' and self.choice in ('midi-lrc','lrc'))
            for widget in self.rows[key][1:]:
                widget.setVisible(visible)
        self.method.setVisible(self.choice == 'scratch')
        self.method_label.setVisible(self.choice == 'scratch')

    def validateCurrentPage(self):
        if self.currentId() == 0:
            if self.choice == 'usdb':
                if self.project is not None:
                    return True
                self.open_usdb()
                return False
            return True
        try:
            paths = {key: field[0].text().strip() for key, field in self.rows.items()}
            if self.choice in ('scratch','lrc'):
                paths['chart'] = ''
            if self.choice not in ('midi-lrc','lrc'):
                paths['lrc'] = ''
            required = ['chart'] if self.choice in ('ultrastar','midi','midi-lrc') else []
            if self.choice in ('midi-lrc','lrc'):
                required.append('lrc')
            for key, value in paths.items():
                if (key in required or value) and not Path(value).is_file():
                    raise ValueError(tr('wizard.missing', name=key))
            if self.choice == 'ultrastar':
                project = import_ultrastar(paths['chart'])
            elif self.choice.startswith('midi'):
                imported = read_midi(paths['chart'])
                labels = [f'{lane.name} / {lane.channel + 1} ({len(lane.notes)})' for lane in imported.lanes]
                from PySide6.QtWidgets import QInputDialog
                label, ok = QInputDialog.getItem(self, tr('Melodiespur'), tr('Spur / Kanal'), labels, 0, False)
                if not ok:
                    return False
                project = project_from_midi(paths['chart'], imported, labels.index(label))
                if paths['lrc']:
                    from studio.lrc import read_lrc, attach_lrc, assign_lrc_notes
                    document = read_lrc(paths['lrc'])
                    attach_lrc(project, document, paths['lrc'])
                    if not any(note.text.strip() for note in project.notes):
                        assign_lrc_notes(project, document)
            else:
                project = StudioProject()
            if paths['media']:
                setattr(project, self.media_kind.currentData() + '_path', paths['media'])
            if paths['cover']:
                project.cover_path = paths['cover']
            from studio.song_media_check import ensure_song_audio
            if not ensure_song_audio(project, self):
                return False
            if self.choice == 'lrc':
                from studio.lrc import read_lrc
                from studio.lyric_timing import lrc_draft
                document = read_lrc(paths['lrc'])
                project = lrc_draft(project,document,paths['lrc'])
                project.title = document.metadata.get('ti', Path(paths['lrc']).stem)
                project.artist = document.metadata.get('ar','')
            project.validate()
            self.project = project
            return True
        except Exception as error:
            QMessageBox.warning(self, 'OpenLips Studio', str(error))
            return False
