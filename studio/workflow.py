"""Persistent, media-first Studio workflow built on the existing editor/services."""
from pathlib import Path
import copy

from PySide6.QtCore import Qt, QSignalBlocker
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QDoubleSpinBox, QComboBox, QCheckBox, QButtonGroup, QProgressBar,
    QFileDialog, QTextEdit, QScrollArea, QMenu, QFrame, QSizePolicy, QLayout)
import qtawesome as qta
from studio.i18n import tr
from studio.branding import asset


def button(text, callback, icon=None, primary=False):
    text = text.replace('&', '&&')
    widget = QPushButton(qta.icon(icon, color='#cdd3d9'), text) if icon else QPushButton(text)
    widget.setMinimumHeight(34)
    widget.clicked.connect(callback)
    if primary:
        widget.setProperty('primary', True)
    return widget


class Waveform(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window, self.samples, self.duration, self.position = window, [], 0., 0.
        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#1c2125'))
        width, height = self.width(), self.height()-26
        if not self.samples:
            painter.setPen(QColor('#a5aeb4'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr('flow.waveform_empty'))
            return
        project = self.window.project
        if project.beat_enabled:
            beat = 60/project.bpm
            start = (project.beat_offset + project.reference_offset) % beat
            painter.setPen(QPen(QColor('#3c5559'), 1))
            while start <= self.duration:
                x = start/max(self.duration, .001)*width
                painter.drawLine(int(x), 0, int(x), height)
                start += beat
        painter.setPen(QPen(QColor('#36bbc3'), 1))
        maximum = max(max(self.samples), .001)
        for index, amplitude in enumerate(self.samples):
            x = index/max(1, len(self.samples)-1)*width
            size = amplitude/maximum*(height*.43)
            painter.drawLine(int(x), int(height/2-size), int(x), int(height/2+size))
        painter.setPen(QColor('#bec7cc'))
        for index in range(5):
            seconds = self.duration*index/4
            painter.drawText(min(width-42, int(width*index/4)), height+20, f'{int(seconds//60):02d}:{int(seconds%60):02d}')
        painter.setPen(QPen(QColor('#ffffff'), 2))
        x = (self.position+project.reference_offset)/max(self.duration, .001)*width
        painter.drawLine(int(x), 0, int(x), height)

    def mousePressEvent(self, event):
        if self.duration:
            self.window.seek(max(0, event.position().x()/max(1, self.width())*self.duration-self.window.project.reference_offset))


class StudioWorkflow:
    def __init__(self, window, editor, tools_menu):
        self.window = window
        window.takeCentralWidget()
        self.worker = self.download = None
        self.current_step = 0
        self.last_media = None
        self.analysis_result = None
        self.updating = False
        self.shell = QWidget()
        self.shell.setObjectName('workflowShell')
        shell = QVBoxLayout(self.shell)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        header = QWidget()
        header.setObjectName('workflowHeader')
        top = QHBoxLayout(header)
        top.setContentsMargins(20, 8, 20, 8)
        brand = QLabel()
        brand.setPixmap(QPixmap(str(asset('app-icon.png'))).scaled(32, 32,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        top.addWidget(brand)
        brand_name = QLabel('OpenLips Studio')
        brand_name.setStyleSheet('font-size: 18px; font-weight: 600; padding-right: 16px;')
        top.addWidget(brand_name)
        self.document_title = QLabel()
        top.addWidget(self.document_title)
        top.addStretch()
        self.saved = QLabel()
        top.addWidget(self.saved)
        save = button('', window.save, 'fa5s.save')
        save.setToolTip(tr('Speichern'))
        top.addWidget(save)
        shell.addWidget(header)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName('workflowSidebar')
        sidebar.setFixedWidth(188)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(10, 22, 10, 12)
        nav.addWidget(button(tr('library.title'), self.show_library, 'fa5s.music'))
        nav.addSpacing(18)
        self.nav_group = QButtonGroup(sidebar)
        self.nav_buttons = []
        for index, key in enumerate(('flow.source', 'flow.prepare', 'flow.lyrics', 'flow.melody', 'flow.export')):
            entry = button(f'{index+1}   {tr(key)}', lambda checked=False, i=index: self.go(i))
            entry.setCheckable(True)
            entry.setMinimumHeight(46)
            entry.setObjectName('workflowStep')
            self.nav_group.addButton(entry)
            self.nav_buttons.append(entry)
            nav.addWidget(entry)
        nav.addStretch()
        community = button(tr('community.title'), window.show_community, 'fa5s.users')
        nav.addWidget(community)
        tools = button(tr('Werkzeuge'), lambda: None, 'fa5s.tools')
        tools.setMenu(tools_menu)
        nav.addWidget(tools)
        settings = button('', window.configure_library, 'fa5s.cog')
        settings.setToolTip(tr('library.directory'))
        nav.addWidget(settings)
        body.addWidget(sidebar)
        window.workspace_tabs.tabBar().hide()
        body.addWidget(window.workspace_tabs, 1)
        shell.addLayout(body, 1)
        window.setCentralWidget(self.shell)
        self.pages = [self.source_page(), self.prepare_page(), self.lyrics_page(), editor, self.export_page()]
        for page in self.pages:
            if window.screens.indexOf(page) < 0:
                window.screens.addWidget(page)
        window.screens.currentChanged.connect(self.stack_changed)
        self.go(0)

    @property
    def busy(self):
        return bool((self.worker and self.worker.isRunning()) or (self.download and self.download.busy))

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
        if self.download:
            self.download.cancel()

    def page(self, title):
        page = QScrollArea()
        page.setWidgetResizable(True)
        content = QWidget()
        page.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(24, 22, 24, 16)
        layout.setSpacing(16)
        label = QLabel(tr(title))
        label.setObjectName('workflowHeading')
        layout.addWidget(label)
        return page, layout

    def footer(self, layout, back, forward, text='flow.next'):
        row = QHBoxLayout()
        row.addWidget(button(tr('flow.back'), lambda: self.go(back), 'fa5s.arrow-left'))
        row.addStretch()
        row.addWidget(button(tr(text), lambda: self.go(forward), 'fa5s.arrow-right', True))
        layout.addLayout(row)

    def source_page(self):
        page, layout = self.page('flow.start')
        modes = QHBoxLayout()
        self.file_mode = button(tr('flow.file'), lambda: self.set_source_mode(False), 'fa5s.file')
        self.url_mode = button(tr('flow.url'), lambda: self.set_source_mode(True), 'fa5s.link')
        group = QButtonGroup(page)
        for item in (self.file_mode, self.url_mode):
            item.setCheckable(True)
            group.addButton(item)
            modes.addWidget(item)
        self.file_mode.setChecked(True)
        modes.addStretch()
        layout.addLayout(modes)
        row = QHBoxLayout()
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText(tr('wizard.media'))
        row.addWidget(self.source_input, 1)
        self.source_action = button(tr('flow.choose_file'), self.acquire_source, 'fa5s.folder-open')
        row.addWidget(self.source_action)
        layout.addLayout(row)
        self.video_download = QCheckBox(tr('Download video (max. 720p)'))
        self.video_download.setChecked(True)
        self.rights = QCheckBox(tr('I have the rights/permission to download the selected media'))
        for widget in (self.video_download, self.rights):
            layout.addWidget(widget)
            widget.hide()
        self.source_status = QLabel()
        self.source_status.setWordWrap(True)
        layout.addWidget(self.source_status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.cancel_download = button(tr('Abbrechen'), lambda: self.download.cancel() if self.download else None, 'fa5s.stop')
        self.cancel_download.hide()
        layout.addWidget(self.cancel_download)
        layout.addSpacing(12)
        row = QHBoxLayout()
        imports = button(tr('flow.import'), self.import_chart, 'fa5s.file-import')
        menu = QMenu(imports)
        for label, callback in ((tr('UltraStar importieren'), self.window.import_txt),
                                (tr('MIDI importieren'), self.window.import_midi),
                                (tr('batch.title'), self.window.import_ultrastar_batch),
                                (tr('download.usdb'), self.window.open_usdb),
                                (tr('welcome.community'), self.window.open_community)):
            menu.addAction(label, callback)
        imports.setMenu(menu)
        row.addWidget(imports)
        row.addWidget(button(tr('Projekt oeffnen'), self.window.open, 'fa5s.folder-open'))
        row.addStretch()
        layout.addLayout(row)
        layout.addStretch()
        footer = QHBoxLayout()
        footer.addWidget(button(tr('flow.empty'), lambda: self.go(3)))
        footer.addStretch()
        footer.addWidget(button(tr('flow.next'), self.continue_source, 'fa5s.arrow-right', True))
        layout.addLayout(footer)
        return page

    def set_source_mode(self, youtube):
        self.url_mode.setChecked(youtube)
        self.file_mode.setChecked(not youtube)
        self.source_input.clear()
        self.source_input.setPlaceholderText(tr('flow.url_placeholder' if youtube else 'wizard.media'))
        self.source_action.setText(tr('flow.download' if youtube else 'flow.choose_file'))
        for item in (self.video_download, self.rights):
            item.setVisible(youtube)

    def import_chart(self):
        self.window.import_txt()

    def acquire_source(self):
        if self.busy:
            return
        if self.url_mode.isChecked():
            self.start_download()
            return
        path = self.source_input.text().strip()
        if not Path(path).is_file():
            path, _ = QFileDialog.getOpenFileName(self.window, tr('flow.choose_file'), '',
                'Media (*.mp4 *.mkv *.mov *.wmv *.webm *.mp3 *.wav *.flac *.m4a *.aac *.ogg *.wma *.xWMA);;All files (*)')
        if path:
            self.window.attempt(lambda: self.adopt_media(path))

    def adopt_media(self, path, video=None, reference='', metadata=None):
        from studio.media_source import AUDIO_EXTENSIONS
        path = Path(path)
        if not path.is_file():
            raise ValueError(tr('flow.no_source'))
        video = path.suffix.lower() not in AUDIO_EXTENSIONS if video is None else video
        project = copy.deepcopy(self.window.project)
        project.video_path, project.audio_path = (str(path), '') if video else ('', str(path))
        project.video_reference = reference
        if video:
            from studio.song_media_check import ensure_song_audio
            if not ensure_song_audio(project, self.window):
                return
        if metadata:
            for name in ('title', 'artist', 'album', 'year'):
                if metadata.get(name):
                    setattr(project, name, str(metadata[name]))
        elif project.title in ('Neuer Song', ''):
            project.title = path.stem
        self.window.stop()
        self.window.snapshot()
        self.window.project = project
        self.source_input.setText(reference or str(path))
        self.window.configure_media()
        self.window.changed()
        self.last_media = None
        self.go(1)

    def continue_source(self):
        entered = self.source_input.text().strip()
        project = self.window.project
        current = project.video_reference if self.url_mode.isChecked() else (project.audio_path or project.video_path)
        if entered and entered != current:
            self.acquire_source()
        elif project.audio_path or project.video_path or project.notes:
            self.go(1)
        else:
            self.source_status.setText(tr('flow.no_source'))

    def start_download(self):
        from studio.source_download import SourceDownload
        self.download = SourceDownload(self.window)
        self.download.progress.connect(self.source_status.setText)
        self.download.failed.connect(self.source_status.setText)
        self.download.ready.connect(lambda value: self.window.attempt(lambda: self.adopt_media(
            value['path'], value['video'], value['reference'], value['metadata'])))
        self.download.finished.connect(self.download_finished)
        try:
            self.download.start(self.source_input.text(), self.video_download.isChecked(), self.rights.isChecked())
        except (ValueError, OSError) as error:
            self.source_status.setText(str(error))
            return
        self.source_action.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.cancel_download.show()
        self.source_status.setText(tr('flow.download_busy'))

    def download_finished(self):
        self.progress.hide()
        self.cancel_download.hide()
        self.source_action.setEnabled(True)
        if self.current_step == 1 and self.download and self.download.completed:
            self.go(1)

    def prepare_page(self):
        page, layout = self.page('flow.prepare_title')
        row = QHBoxLayout()
        self.prep_cover = QLabel()
        self.prep_cover.setFixedSize(100, 100)
        row.addWidget(self.prep_cover)
        fields = QHBoxLayout()
        self.prep_title, self.prep_artist = QLineEdit(), QLineEdit()
        for label, widget in ((tr('Titel'), self.prep_title), (tr('Artist'), self.prep_artist)):
            column = QVBoxLayout()
            column.addWidget(QLabel(label))
            column.addWidget(widget)
            fields.addLayout(column)
        row.addLayout(fields, 1)
        row.addWidget(button('', self.window.load_cover, 'fa5s.image'))
        layout.addLayout(row)
        self.source_summary = QLabel()
        self.source_summary.setWordWrap(True)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source_summary, 1)
        source_row.addWidget(button(tr('flow.replace_source'), lambda: self.go(0), 'fa5s.sync-alt'))
        layout.addLayout(source_row)
        row = QHBoxLayout()
        tempo, key = QVBoxLayout(), QVBoxLayout()
        tempo.addWidget(QLabel('BPM'))
        numbers = QHBoxLayout()
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(1, 1000)
        self.bpm.setDecimals(2)
        numbers.addWidget(self.bpm, 1)
        for text, factor in (('1/2', .5), ('2x', 2)):
            numbers.addWidget(button(text, lambda checked=False, f=factor: self.bpm.setValue(self.bpm.value()*f)))
        tempo.addLayout(numbers)
        tempo.addWidget(QLabel(tr('beat.offset')))
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-86400, 86400)
        self.offset.setDecimals(3)
        self.offset.setSingleStep(.01)
        self.offset.setSuffix(' s')
        tempo.addWidget(self.offset)
        self.ticks = QCheckBox(tr('flow.metronome'))
        self.ticks.toggled.connect(self.commit_preparation)
        tempo.addWidget(self.ticks)
        key.addWidget(QLabel(tr('key.title')))
        self.key = QComboBox()
        self.key.addItem(tr('key.none'), '')
        from studio.keys import ROOTS
        for root in ROOTS:
            for minor in (False, True):
                self.key.addItem(f'{root} {tr("key.minor" if minor else "key.major")}', root+('m' if minor else ''))
        key.addWidget(self.key)
        self.proposal = QLabel()
        self.proposal.setWordWrap(True)
        self.proposal.setObjectName('workflowProposal')
        key.addWidget(self.proposal)
        self.detect_button = button(tr('flow.detect'), self.analyze, 'fa5s.sync-alt')
        key.addWidget(self.detect_button)
        key.addStretch()
        row.addLayout(tempo, 1)
        row.addSpacing(32)
        row.addLayout(key, 1)
        layout.addLayout(row)
        self.waveform = Waveform(self.window)
        layout.addWidget(self.waveform, 1)
        transport = QHBoxLayout()
        self.prep_play = button('', self.window.toggle_play, 'fa5s.play')
        self.prep_play.setToolTip(tr('Wiedergabe / Pause'))
        transport.addWidget(self.prep_play)
        transport.addWidget(button('', self.window.stop, 'fa5s.stop'))
        self.prep_clock = QLabel('00:00.000')
        transport.addWidget(self.prep_clock)
        transport.addStretch()
        layout.addLayout(transport)
        self.footer(layout, 0, 2, 'flow.next_lyrics')
        for item in (self.bpm, self.offset, self.prep_title, self.prep_artist):
            item.editingFinished.connect(self.commit_preparation)
        self.key.activated.connect(self.commit_preparation)
        return page

    def lyrics_page(self):
        page, layout = self.page('flow.lyrics_title')
        row = QHBoxLayout()
        for text, callback, icon in (('flow.lyrics_file', self.load_lyrics, 'fa5s.file-import'),
                                     ('Lyrics suchen', self.window.search_lyrics, 'fa5s.search'),
                                     ('flow.transcribe', lambda: self.window.ai_chart_dialog(lyrics_only=True), 'fa5s.microphone')):
            row.addWidget(button(tr(text), callback, icon))
        row.addStretch()
        layout.addLayout(row)
        self.text_input = QTextEdit()
        self.text_input.setAcceptRichText(False)
        self.text_input.setDocument(self.window.lyrics.document())
        self.text_input.setStyleSheet('QTextEdit {font-size: 18px; padding: 16px; border: 0;}')
        layout.addWidget(self.text_input, 1)
        row = QHBoxLayout()
        row.addWidget(button(tr('flow.timing'), self.window.timing_assistant, 'fa5s.keyboard'))
        row.addWidget(button(tr('flow.grid_draft'), self.grid_draft, 'fa5s.th'))
        row.addStretch()
        layout.addLayout(row)
        self.footer(layout, 1, 3, 'flow.next_melody')
        return page

    def load_lyrics(self):
        path, _ = QFileDialog.getOpenFileName(self.window, tr('flow.lyrics_file'), '', 'Lyrics (*.lrc *.txt)')
        if not path:
            return
        def load():
            if Path(path).suffix.lower() == '.lrc':
                from studio.lrc import read_lrc
                self.window.accept_lrc(read_lrc(path), path)
            else:
                self.window.snapshot()
                self.window.lyrics.setPlainText(Path(path).read_text(encoding='utf-8-sig'))
                self.window.changed()
        self.window.attempt(load)

    def grid_draft(self):
        def create():
            if self.window.project.notes:
                self.window.beat_grid_dialog()
                return
            from studio.lyric_timing import text_units, timed_draft
            units = text_units(self.window.lyrics.toPlainText())
            if not units:
                raise ValueError(tr('flow.no_lyrics'))
            project = self.window.project
            step = 60/project.bpm
            onsets = [max(0, project.beat_offset)+index*step for index in range(len(units))]
            candidate = timed_draft(project, onsets, self.window.lyrics.toPlainText(), end=onsets[-1]+step)
            candidate.beat_enabled = True
            self.window.snapshot()
            self.window.project = candidate
            self.window.changed()
            self.go(3)
        self.window.attempt(create)

    def export_page(self):
        page, layout = self.page('flow.export_title')
        self.review_summary = QLabel()
        self.review_summary.setWordWrap(True)
        layout.addWidget(self.review_summary)
        for text, callback, icon in (('flow.review_notes', self.window.review_chart, 'fa5s.search'),
                                     ('review.title', self.window.guided_review, 'fa5s.headphones'),
                                     ('pages.smart', self.window.intelligent_lyric_pages, 'fa5s.stream')):
            layout.addWidget(button(tr(text), callback, icon))
        layout.addStretch()
        for text, callback in (('export.community', self.window.export_community),
                               ('DLC exportieren (experimentell)', self.window.export_dlc),
                               ('pack.title', self.window.export_song_pack)):
            layout.addWidget(button(tr(text), callback, 'fa5s.file-export', True))
        row = QHBoxLayout()
        row.addWidget(button(tr('flow.back'), lambda: self.go(3), 'fa5s.arrow-left'))
        row.addStretch()
        row.addWidget(button(tr('Speichern'), self.window.save, 'fa5s.save'))
        layout.addLayout(row)
        return page

    def show_library(self):
        if not self.window.library_action.isChecked():
            self.window.library_action.setChecked(True)
            self.window.toggle_library(True)
        if self.window.library_page:
            self.window.workspace_tabs.setCurrentWidget(self.window.library_page)

    def stack_changed(self):
        page = self.window.screens.currentWidget()
        if page in self.pages:
            self.current_step = self.pages.index(page)
            self.nav_buttons[self.current_step].setChecked(True)

    def go(self, step):
        if self.current_step == 1 and step != 1:
            self.commit_preparation()
        self.current_step = step
        self.window.workspace_tabs.setCurrentWidget(self.window.screens)
        self.window.screens.setCurrentWidget(self.pages[step])
        self.nav_buttons[step].setChecked(True)
        self.refresh()
        if step == 1:
            source = (self.window.project.audio_path, self.window.project.video_path)
            if any(source) and source != self.last_media and not self.busy:
                self.analyze()

    def commit_preparation(self, *_):
        if self.updating:
            return
        project = self.window.project
        values = (self.prep_title.text(), self.prep_artist.text(), self.bpm.value(), self.key.currentData() or '',
                  self.offset.value(), self.ticks.isChecked())
        old = (project.title, project.artist, project.bpm, project.key_signature, project.beat_offset, project.beat_ticks)
        if values == old:
            return
        self.window.snapshot()
        project.title, project.artist, project.bpm, project.key_signature, project.beat_offset, project.beat_ticks = values
        project.beat_enabled = True
        self.window.changed()
        self.waveform.update()

    def analyze(self):
        if self.worker and self.worker.isRunning():
            return
        from studio.song_analysis import SongAnalysis
        source = (self.window.project.audio_path, self.window.project.video_path)
        if not any(source):
            self.proposal.setText(tr('flow.no_media'))
            return
        self.commit_preparation()
        self.last_media = source
        self.worker = SongAnalysis(self.window.project, self.window)
        self.worker.ready.connect(lambda result: self.analysis_ready(result, source))
        self.worker.failed.connect(self.proposal.setText)
        self.worker.finished.connect(lambda: self.detect_button.setEnabled(True))
        self.detect_button.setEnabled(False)
        self.proposal.setText(tr('flow.analyzing'))
        self.worker.start()

    def analysis_ready(self, result, source):
        if source != (self.window.project.audio_path, self.window.project.video_path):
            return
        self.analysis_result = result
        self.updating = True
        if result['bpm']:
            self.bpm.setValue(result['bpm'])
            self.offset.setValue(result['offset'])
        if result['key']:
            index = self.key.findData(result['key'])
            if index >= 0:
                self.key.setCurrentIndex(index)
        self.updating = False
        self.waveform.samples, self.waveform.duration = result['waveform'], result['duration']
        self.waveform.update()
        self.window.editor_waveform.samples = result['waveform']
        self.window.editor_waveform.duration = result['duration']
        self.window.editor_waveform.show()
        self.proposal.setText(tr('flow.analysis_result') + ('\n'+'\n'.join(result['warnings']) if result['warnings'] else ''))

    def refresh(self):
        project = self.window.project
        self.updating = True
        for widget, value in ((self.prep_title, project.title), (self.prep_artist, project.artist)):
            if not widget.hasFocus():
                widget.setText(value)
        # A pending detection proposal belongs to preparation until explicitly accepted.
        if not self.analysis_result or self.current_step != 1:
            for widget, value in ((self.bpm, project.bpm), (self.offset, project.beat_offset)):
                if not widget.hasFocus():
                    widget.setValue(value)
            self.key.setCurrentIndex(max(0, self.key.findData(project.key_signature)))
        self.ticks.setChecked(project.beat_ticks)
        self.updating = False
        source = project.audio_path or project.video_path
        self.source_summary.setText(project.video_reference or (Path(source).name if source else tr('flow.no_media')))
        self.source_summary.setToolTip(project.video_reference or source)
        self.document_title.setText(project.title)
        self.saved.setText(tr('flow.unsaved' if self.window.dirty else 'flow.saved' if self.window.path else 'flow.session'))
        from studio.media import cover_image
        try:
            cover = QPixmap.fromImage(cover_image(project)) if project.cover_path else QPixmap(str(asset('app-icon.png')))
            self.prep_cover.setPixmap(cover.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        except ValueError:
            self.prep_cover.clear()
        self.review_summary.setText(tr('flow.summary', notes=len(project.notes),
            missing=sum(not n.text.strip() for n in project.notes), unpitched=sum(not n.pitch_assigned for n in project.notes)))

    def position_changed(self, seconds):
        self.prep_clock.setText(f'{int(seconds//60):02d}:{seconds%60:06.3f}')
        self.waveform.position = seconds
        if self.current_step == 1:
            self.waveform.update()
        self.prep_play.setIcon(qta.icon('fa5s.pause' if self.window.playing else 'fa5s.play', color='#cdd3d9'))
