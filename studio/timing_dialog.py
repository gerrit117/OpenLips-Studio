"""Local tap-to-time assistant with reference playback and onset tick review."""
import copy
from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer, QUrl, QEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QLineEdit, QAbstractSpinBox, QComboBox, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QSlider, QCheckBox, QFileDialog,
    QRadioButton, QButtonGroup, QDialogButtonBox)
import qtawesome as qta

from studio.i18n import tr
from studio.model import EditorNote
from studio.lyric_timing import text_units, write_lrc
from studio.tone_preview import TonePreview


class TimingDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('timing.title'))
        self.resize(820, 640)
        self.original = copy.deepcopy(project)
        self.project = None
        self.notes, self.history, self.future = [], [], []
        self.position, self.playing, self.clock_start = 0., False, 0.
        self.rate, self.rendering = 1., False
        self.last_tick = 0.
        self.media = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.65)
        self.media.setAudioOutput(self.audio)
        self.click = TonePreview(self)
        self.click.set_volume(.5)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        layout = QVBoxLayout(self)
        source_row = QHBoxLayout()
        self.reference = QLabel()
        self.reference.setWordWrap(True)
        source_row.addWidget(self.reference, 1)
        source = QPushButton(qta.icon('fa5s.folder-open',color='#cdd3d9'), tr('wizard.media'))
        source.clicked.connect(self.choose_media)
        source_row.addWidget(source)
        layout.addLayout(source_row)
        self.text = QPlainTextEdit(project.draft_lyrics or project.lyric_text())
        self.text.setPlaceholderText(tr('Songtext'))
        self.text.setMaximumHeight(130)
        layout.addWidget(self.text)
        units = QHBoxLayout()
        self.words = QRadioButton(tr('timing.words'))
        self.syllables = QRadioButton(tr('timing.syllables'))
        self.syllables.setToolTip(tr('Silben mit | trennen'))
        self.group = QButtonGroup(self)
        self.group.addButton(self.words)
        self.group.addButton(self.syllables)
        self.words.setChecked(True)
        units.addWidget(self.words)
        units.addWidget(self.syllables)
        self.next_label = QLabel()
        self.next_label.setWordWrap(True)
        units.addWidget(self.next_label, 1)
        layout.addLayout(units)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([tr('Start'), tr('Laenge'), tr('Text')])
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.table, 1)
        self.seek_bar = QSlider(Qt.Orientation.Horizontal)
        self.seek_bar.setRange(0, 300000)
        self.seek_bar.sliderMoved.connect(lambda value:self.seek(value/1000))
        layout.addWidget(self.seek_bar)
        transport = QHBoxLayout()
        self.play = QPushButton(qta.icon('fa5s.play',color='#cdd3d9'), '')
        self.play.setFixedSize(36,32)
        self.play.setToolTip(tr('timing.play'))
        self.play.clicked.connect(self.toggle_play)
        transport.addWidget(self.play)
        self.play_selection = QPushButton(qta.icon('fa5s.step-forward',color='#cdd3d9'), '')
        self.play_selection.setFixedSize(36,32)
        self.play_selection.setToolTip(tr('timing.play_selection'))
        self.play_selection.clicked.connect(self.play_selected)
        self.play_selection.setEnabled(False)
        transport.addWidget(self.play_selection)
        self.record = QPushButton(qta.icon('fa5s.record-vinyl',color='#cdd3d9'),tr('timing.record'))
        self.record.setCheckable(True)
        self.record.setToolTip(tr('timing.record_tip'))
        self.record.toggled.connect(self.arm)
        transport.addWidget(self.record)
        self.clock = QLabel('00:00.000')
        transport.addWidget(self.clock)
        self.speed = QComboBox()
        self.speed.addItems(['0.5x','0.75x','1x'])
        self.speed.setCurrentText('1x')
        self.speed.setFixedWidth(68)
        self.speed.currentTextChanged.connect(self.change_speed)
        transport.addWidget(self.speed)
        self.hear_ticks = QCheckBox(tr('timing.ticks'))
        self.hear_ticks.setChecked(True)
        transport.addWidget(self.hear_ticks)
        self.tick_volume = QSlider(Qt.Orientation.Horizontal)
        self.tick_volume.setRange(0,100)
        self.tick_volume.setValue(50)
        self.tick_volume.setMaximumWidth(85)
        self.tick_volume.setToolTip(tr('timing.tick_volume'))
        self.tick_volume.valueChanged.connect(lambda value:self.click.set_volume(value/100))
        transport.addWidget(self.tick_volume)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0,100)
        self.volume.setValue(65)
        self.volume.setMaximumWidth(85)
        self.volume.setToolTip(tr('reference.volume'))
        reference_icon = QLabel()
        reference_icon.setPixmap(qta.icon('fa5s.headphones',color='#cdd3d9').pixmap(16,16))
        reference_icon.setToolTip(tr('reference.volume'))
        transport.addWidget(reference_icon)
        self.volume.valueChanged.connect(lambda value:self.audio.setVolume(value/100))
        transport.addWidget(self.volume)
        layout.addLayout(transport)
        actions = QHBoxLayout()
        for label, icon, callback in [('Rueckgaengig','fa5s.undo',self.undo),
            ('Wiederholen','fa5s.redo',self.redo),('timing.retake','fa5s.redo-alt',self.retake),
            ('timing.clear','fa5s.trash-alt',self.clear),('timing.lrc_export','fa5s.file-export',self.export_lrc)]:
            button = QPushButton(qta.icon(icon,color='#cdd3d9'),tr(label))
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status = QLabel(tr('timing.estimated'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('timing.accept'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Abbrechen'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.text.textChanged.connect(self.assign_text)
        self.group.buttonToggled.connect(lambda button, checked:self.assign_text() if checked else None)
        self.table.itemChanged.connect(self.table_edited)
        self.table.currentCellChanged.connect(self.selection_changed)
        self.media.errorOccurred.connect(lambda *_:self.status.setText(self.media.errorString()))
        self.click.failed.connect(self.status.setText)
        self.configure_media()
        self.update_next()
        QApplication.instance().installEventFilter(self)

    def units(self):
        return text_units(self.text.toPlainText(),'syllable' if self.syllables.isChecked() else 'word')

    def configure_media(self):
        path = self.original.audio_path or self.original.video_path
        self.reference.setText(Path(path).name if path else tr('Keine Referenz'))
        self.media.setSource(QUrl.fromLocalFile(path) if path else QUrl())
        self.seek(self.position)

    def choose_media(self):
        if self.playing:
            self.toggle_play()
        path,_ = QFileDialog.getOpenFileName(self,tr('wizard.media'),'',
            'Media (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.mp4 *.mkv *.webm *.wmv);;All files (*)')
        if path:
            candidate = copy.deepcopy(self.original)
            candidate.audio_path = candidate.video_path = ''
            field = 'video_path' if Path(path).suffix.lower() in ('.mp4','.mkv','.webm','.wmv') else 'audio_path'
            setattr(candidate,field,path)
            from studio.song_media_check import ensure_song_audio
            if ensure_song_audio(candidate,self):
                self.original = candidate
                self.configure_media()

    def state(self, position=None, row=None):
        return dict(notes=copy.deepcopy(self.notes), position=self.position if position is None else position,
                    row=self.table.currentRow() if row is None else row)

    def snapshot(self, position=None, row=None):
        self.history.append(self.state(position, row))
        self.history = self.history[-100:]
        self.future.clear()

    def update_next(self):
        units = self.units()
        next_text = units[len(self.notes)].text if len(self.notes)<len(units) else tr('timing.end') if units else tr('timing.blank')
        self.next_label.setText(tr('timing.next', text=next_text, count=len(self.notes), total=len(units)))

    def render(self):
        selected_row = self.table.currentRow()
        self.rendering = True
        self.table.setRowCount(len(self.notes))
        for row,n in enumerate(self.notes):
            for column,value in enumerate((f'{n.time:.3f}',f'{n.length:.3f}',n.text)):
                self.table.setItem(row,column,QTableWidgetItem(value))
        if self.notes:
            self.table.setCurrentCell(min(max(0, selected_row), len(self.notes)-1), 0)
        self.rendering = False
        self.play_selection.setEnabled(bool(self.notes) and not self.record.isChecked())
        self.update_next()

    def table_edited(self, item):
        if self.rendering:
            return
        try:
            candidate = self.read_rows()
            if candidate != self.notes:
                row = item.row()
                if item.column() == 0 and candidate[row].time != self.notes[row].time:
                    old = self.notes[row]
                    end = old.time + old.length
                    if candidate[row].time >= end:
                        raise ValueError(tr('timing.before_end'))
                    candidate[row].length = end-candidate[row].time
                    if row and abs(self.notes[row-1].time+self.notes[row-1].length-old.time) < .001:
                        candidate[row-1].length = candidate[row].time-candidate[row-1].time
                self.snapshot(self.notes[row].time, row)
                self.notes = candidate
                self.render()
                self.seek(self.notes[row].time)
                self.status.setText(tr('timing.estimated'))
        except ValueError as error:
            self.status.setText(str(error))

    def selection_changed(self, row, *_):
        self.play_selection.setEnabled(0 <= row < len(self.notes) and not self.record.isChecked())
        if not self.rendering and not self.record.isChecked() and 0 <= row < len(self.notes):
            self.seek(self.notes[row].time)

    def play_selected(self):
        row = self.table.currentRow()
        if not self.record.isChecked() and 0 <= row < len(self.notes):
            self.seek(self.notes[row].time)
            if not self.playing:
                self.toggle_play()

    def read_rows(self):
        notes = copy.deepcopy(self.notes)
        for row,n in enumerate(notes):
            n.time = float(self.table.item(row,0).text().replace(',','.'))
            n.length = float(self.table.item(row,1).text().replace(',','.'))
            n.text = self.table.item(row,2).text()
            n.validate()
            if n.time>86400 or n.length>86400:
                raise ValueError('Timing must fit within 24 hours')
        if any(b.time <= a.time for a,b in zip(notes,notes[1:])):
            raise ValueError(tr('timing.order'))
        return notes

    def assign_text(self):
        try:
            units = self.units()
            self.notes = self.read_rows()
            if self.notes:
                self.snapshot()
            for index,note in enumerate(self.notes):
                if index < len(units):
                    unit = units[index]
                    note.text, note.end_word = unit.text, unit.end_word
                    note.line_break_after = unit.end_line and index+1<len(self.notes)
            self.render()
        except ValueError as error:
            self.status.setText(str(error))

    def arm(self, enabled):
        self.text.setEnabled(not enabled)
        self.words.setEnabled(not enabled)
        self.syllables.setEnabled(not enabled)
        self.table.setEnabled(not enabled)
        self.play_selection.setEnabled(not enabled and 0 <= self.table.currentRow() < len(self.notes))
        if enabled:
            self.table.setFocus()
            if not self.playing:
                self.toggle_play()
        elif self.notes and self.position > self.notes[-1].time+.001:
            self.snapshot(self.notes[-1].time, len(self.notes)-1)
            self.notes[-1].length = round(self.position,3)-self.notes[-1].time
            self.render()

    def tap(self):
        if not self.record.isChecked() or not self.playing:
            return
        self.tick()
        if self.notes and self.position <= self.notes[-1].time+.02:
            return
        units = self.units()
        if units and len(self.notes)>=len(units):
            self.record.setChecked(False)
            return
        onset = round(self.position,3)
        self.snapshot(onset, len(self.notes))
        if self.notes:
            self.notes[-1].length = onset-self.notes[-1].time
            self.notes[-1].line_break_after = units[len(self.notes)-1].end_line if units else False
        unit = units[len(self.notes)] if len(self.notes)<len(units) else None
        self.notes.append(EditorNote(onset,2,60,unit.text if unit else '',
            unit.end_word if unit else True,pitch_assigned=False))
        self.rendering = True
        row = len(self.notes)-1
        if row:
            self.table.item(row-1,1).setText(f'{self.notes[row-1].length:.3f}')
        self.table.insertRow(row)
        note = self.notes[-1]
        for column,value in enumerate((f'{note.time:.3f}',f'{note.length:.3f}',note.text)):
            self.table.setItem(row,column,QTableWidgetItem(value))
        self.rendering = False
        self.update_next()
        self.table.scrollToBottom()
        if self.hear_ticks.isChecked():
            self.click.play(96,.03)

    def seek(self, seconds):
        self.position = max(0,seconds)
        self.clock_start = time.monotonic()-self.position/self.rate
        self.media.setPosition(round(max(0,self.position+self.original.reference_offset)*1000))
        self.last_tick = self.position-1e-6
        self.update_clock()

    def toggle_play(self):
        self.playing = not self.playing
        if self.playing:
            self.clock_start = time.monotonic()-self.position/self.rate
            self.last_tick = self.position-1e-6
            if self.position+self.original.reference_offset>=0:
                self.media.setPosition(round((self.position+self.original.reference_offset)*1000))
                self.media.play()
            self.timer.start()
        else:
            self.media.pause()
            self.timer.stop()
            self.click.stop()
        self.play.setIcon(qta.icon('fa5s.pause' if self.playing else 'fa5s.play',color='#cdd3d9'))

    def change_speed(self, text):
        self.rate = float(text.rstrip('x'))
        self.media.setPlaybackRate(self.rate)
        self.clock_start = time.monotonic()-self.position/self.rate

    def update_clock(self):
        self.clock.setText(f'{int(self.position//60):02d}:{self.position%60:06.3f}')
        maximum = max(300000,self.media.duration(),round(self.position*1000)+1000)
        self.seek_bar.setMaximum(maximum)
        if not self.seek_bar.isSliderDown():
            self.seek_bar.setValue(round(self.position*1000))

    def tick(self):
        if not self.playing:
            return
        if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.position = max(0,self.media.position()/1000-self.original.reference_offset)
            self.clock_start = time.monotonic()-self.position/self.rate
        else:
            self.position = (time.monotonic()-self.clock_start)*self.rate
            media_time = self.position+self.original.reference_offset
            if media_time>=0 and (self.original.audio_path or self.original.video_path):
                self.media.setPosition(round(media_time*1000))
                self.media.play()
        if not self.record.isChecked() and self.hear_ticks.isChecked():
            if any(self.last_tick<n.time<=self.position for n in self.notes):
                self.click.play(96,.03)
        self.last_tick = self.position
        self.update_clock()
        if self.media.duration() and self.position+self.original.reference_offset>=self.media.duration()/1000:
            self.record.setChecked(False)
            self.toggle_play()

    def undo(self):
        if self.history:
            state = self.history.pop()
            row = state['row']
            position = self.notes[row].time if 0 <= row < len(self.notes) else state['position']
            self.future.append(self.state(position, row))
            self.restore(state)

    def redo(self):
        if self.future:
            state = self.future.pop()
            row = state['row']
            position = self.notes[row].time if 0 <= row < len(self.notes) else state['position']
            self.history.append(self.state(position, row))
            self.restore(state)

    def restore(self, state):
        self.notes = state['notes']
        self.render()
        if 0 <= state['row'] < len(self.notes):
            self.table.setCurrentCell(state['row'], 0)
        self.seek(state['position'])

    def retake(self):
        row = self.table.currentRow()
        if row>=0:
            self.record.setChecked(False)
            self.snapshot()
            self.notes = self.read_rows()
            position = self.notes[row].time
            self.notes = self.notes[:row]
            self.seek(max(0,position-.5))
            self.render()
            self.record.setChecked(True)

    def clear(self):
        self.record.setChecked(False)
        self.snapshot()
        self.notes = []
        self.render()
        self.seek(0)

    def candidate(self):
        candidate = copy.deepcopy(self.original)
        candidate.notes = self.read_rows()
        if not candidate.notes:
            raise ValueError(tr('timing.need_taps'))
        candidate.draft_lyrics = self.text.toPlainText()
        candidate.source = 'Lyric timing draft'
        candidate.page_layout_mode = 'automatic'
        candidate.validate()
        return candidate

    def export_lrc(self):
        path,_ = QFileDialog.getSaveFileName(self,tr('timing.lrc_export'),'', 'LRC (*.lrc)')
        if path:
            try:
                write_lrc(self.candidate(),path)
                self.status.setText(tr('export.saved',path=path))
            except (ValueError,OSError) as error:
                self.status.setText(str(error))

    def accept(self):
        try:
            self.record.setChecked(False)
            self.project = self.candidate()
            super().accept()
        except ValueError as error:
            self.status.setText(str(error))

    def eventFilter(self, watched, event):
        if (event.type()==QEvent.Type.KeyPress and self.record.isChecked()
            and hasattr(watched,'window') and watched.window() is self
            and event.modifiers()==Qt.KeyboardModifier.NoModifier):
            if event.key()==Qt.Key.Key_Space:
                if not event.isAutoRepeat():
                    self.tap()
                return True
        return super().eventFilter(watched,event)

    def done(self, result):
        self.timer.stop()
        self.media.stop()
        self.click.stop()
        QApplication.instance().removeEventFilter(self)
        super().done(result)
