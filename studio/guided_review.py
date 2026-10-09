"""Transactional, line-by-line review shared by AI and plugin drafts."""
import copy
import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
    QLabel, QPushButton, QCheckBox, QSlider, QSplitter, QWidget,
    QDialogButtonBox, QComboBox)
import qtawesome as qta

from studio.i18n import tr
from studio.model import StudioProject
from studio.timeline import Timeline
from studio.tone_preview import TonePreview


def review_lines(project):
    """Use supplied lyric anchors; otherwise use the existing chart phrases."""
    end = max((n.time + n.length for n in project.notes), default=1)
    if project.lyric_reference.get('raw'):
        from studio.lrc import parse_lrc
        document = parse_lrc(project.lyric_reference['raw'])
        lines = [(cue.time, max(cue.time + .1, document.cues[i + 1].time
                if i + 1 < len(document.cues) else end), cue.text)
                for i, cue in enumerate(document.cues)]
        intro = [n for n in project.notes if n.time < document.cues[0].time]
        if intro:
            lines.insert(0, (min(n.time for n in intro), document.cues[0].time, ''))
        return lines
    groups, group = [], []
    for note in project.ordered():
        if group and (note.time - (group[-1].time + group[-1].length) > .75 or
                      note.time - group[0].time >= 8):
            groups.append(group)
            group = []
        group.append(note)
        if note.line_break_after:
            groups.append(group)
            group = []
    if group:
        groups.append(group)
    return [(g[0].time, max(n.time + n.length for n in g),
             ' '.join(n.text for n in g if n.text.strip())) for g in groups]


def review_draft(result, reference):
    candidate = copy.deepcopy(reference)
    candidate.notes = copy.deepcopy(result.notes)
    candidate.source = result.source
    candidate.warnings = list(result.warnings)
    if result.lyric_reference:
        candidate.lyric_reference = copy.deepcopy(result.lyric_reference)
    if result.draft_lyrics:
        candidate.draft_lyrics = result.draft_lyrics
    if not candidate.audio_path and not candidate.video_path:
        candidate.audio_path = result.audio_path
    if candidate.lyric_reference.get('raw') and not any(n.text.strip() for n in candidate.notes):
        from studio.lrc import parse_lrc
        from studio.ai_chart import PitchSpan, notes_from_analysis, words_from_lrc
        words, notices = words_from_lrc(parse_lrc(candidate.lyric_reference['raw']),
            max((n.time + n.length for n in candidate.notes), default=1))
        pitches = [PitchSpan(n.time, n.time + n.length, n.pitch) for n in candidate.ordered()]
        if all(a.end <= b.start + 1e-6 for a, b in zip(pitches, pitches[1:])):
            candidate.notes, warnings = notes_from_analysis(pitches, words)
            candidate.warnings.extend(notices + warnings)
    return candidate


class GuidedReviewDialog(QDialog):
    def __init__(self, project, parent=None, *, audio_path=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.lines = review_lines(self.project)
        self.history, self.future = [], []
        self.playing = False
        self.sounding = None
        self.setWindowTitle(tr('review.title'))
        self.resize(1080, 700)
        root = QVBoxLayout(self)
        split = QSplitter()
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for i, (start, end, text) in enumerate(self.lines):
            self.list.addItem(f'{i + 1}. {int(start // 60):02d}:{start % 60:05.2f}  {text}')
            self.list.item(i).setToolTip(text)
        split.addWidget(self.list)
        right = QWidget()
        layout = QVBoxLayout(right)
        self.lyric = QLabel()
        self.lyric.setTextFormat(Qt.TextFormat.PlainText)
        self.lyric.setWordWrap(True)
        self.lyric.setStyleSheet('font-size: 18px; padding: 6px;')
        layout.addWidget(self.lyric)
        self.timeline = Timeline()
        self.timeline.follow = False
        self.timeline.snap = False
        self.view = StudioProject(key_signature=project.key_signature, bpm=project.bpm)
        layout.addWidget(self.timeline, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        split.addWidget(right)
        split.setSizes([250, 800])
        root.addWidget(split, 1)
        transport = QHBoxLayout()
        self.play = QPushButton(qta.icon('fa5s.play', color='#cdd3d9'), '')
        self.play.setToolTip(tr('Wiedergabe / Pause'))
        self.play.clicked.connect(self.toggle_play)
        transport.addWidget(self.play)
        self.loop = QCheckBox(tr('review.loop'))
        self.loop.setChecked(True)
        transport.addWidget(self.loop)
        self.mode = QComboBox()
        for label, value in [('review.both', 'both'), ('review.recording', 'recording'), ('review.notes', 'notes')]:
            self.mode.addItem(tr(label), value)
        self.mode.currentIndexChanged.connect(self.set_mode)
        transport.addWidget(self.mode)
        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.tones = TonePreview(self)
        self.offset = 0 if audio_path else project.reference_offset
        source = audio_path or project.audio_path or project.video_path
        if source:
            self.player.setSource(QUrl.fromLocalFile(source))
        self.player.errorOccurred.connect(self.media_error)
        self.tones.failed.connect(self.status.setText)
        for label, default, callback in [('review.recording', 45, lambda v: self.audio.setVolume(v / 100)),
                                          ('review.notes', 70, lambda v: self.tones.set_volume(v / 100))]:
            transport.addWidget(QLabel(tr(label)))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setFixedWidth(110)
            slider.setToolTip(tr(label))
            slider.valueChanged.connect(callback)
            slider.setValue(default)
            transport.addWidget(slider)
        self.speed = QComboBox()
        for rate in (1.0, .75, .5):
            self.speed.addItem(f'{rate:g}x', rate)
        self.speed.currentIndexChanged.connect(self.speed_changed)
        transport.addWidget(self.speed)
        root.addLayout(transport)
        controls = QHBoxLayout()
        for label, icon, callback in [('review.previous', 'fa5s.chevron-left', lambda: self.navigate(-1)),
                                     ('review.next', 'fa5s.chevron-right', lambda: self.navigate(1)),
                                     ('Rueckgaengig', 'fa5s.undo', self.undo),
                                     ('Wiederholen', 'fa5s.redo', self.redo)]:
            button = QPushButton(qta.icon(icon, color='#cdd3d9'), tr(label))
            button.clicked.connect(callback)
            controls.addWidget(button)
        self.checked = QCheckBox(tr('review.checked'))
        self.checked.toggled.connect(self.mark_checked)
        self.reviewed = set()
        controls.addWidget(self.checked)
        controls.addStretch()
        root.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('review.apply'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Abbrechen'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.timeline.before_edit.connect(self.snapshot)
        self.timeline.edited.connect(self.edited)
        self.timeline.selected.connect(self.preview_selected)
        self.timeline.pitch_preview.connect(lambda pitch: self.preview_tone(pitch))
        self.timeline.seek.connect(self.seek)
        self.list.currentRowChanged.connect(self.select_line)
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        for key, callback in [('Space', self.toggle_play), ('Ctrl+Z', self.undo), ('Ctrl+Shift+Z', self.redo)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
        if self.lines:
            self.list.setCurrentRow(0)
        else:
            self.play.setEnabled(False)
        self.set_mode()

    def select_line(self, row):
        self.stop()
        if not 0 <= row < len(self.lines):
            return
        self.start, self.end, text = self.lines[row]
        self.lyric.setText(text or tr('review.no_text'))
        self.checked.blockSignals(True)
        self.checked.setChecked(row in self.reviewed)
        self.checked.blockSignals(False)
        self.refresh()
        self.position = max(0, self.start - .2)
        self.seek(self.position)

    def refresh(self):
        self.view.notes = [n for n in self.project.ordered()
                           if n.time < self.end and n.time + n.length > self.start]
        self.timeline.set_project(self.view)
        self.timeline.origin = max(0, self.start - .25)
        self.timeline.scale = max(12, (self.timeline.width() - 85) / max(1, self.end - self.start + .5))
        self.timeline.update()
        problems = sum(not n.pitch_assigned or n.length < .08 for n in self.view.notes)
        self.status.setText(tr('review.check', count=problems) if problems else '')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'start'):
            self.refresh()

    def snapshot(self):
        self.history.append(copy.deepcopy(self.project.notes))
        self.history = self.history[-100:]
        self.future.clear()

    def edited(self):
        # Timeline replaces its filtered list when merging/deleting notes.
        visible = {n.id for n in self.project.notes if n.time < self.end and n.time + n.length > self.start}
        original = {n.id for n in self.view.notes}
        self.project.notes = [n for n in self.project.notes if n.id not in visible or n.id in original]
        known = {n.id for n in self.project.notes}
        self.project.notes.extend(n for n in self.view.notes if n.id not in known)
        self.refresh()
        self.reviewed.discard(self.list.currentRow())
        self.checked.setChecked(False)

    def undo(self):
        if self.history:
            self.stop()
            self.future.append(copy.deepcopy(self.project.notes))
            self.project.notes = self.history.pop()
            self.refresh()

    def redo(self):
        if self.future:
            self.stop()
            self.history.append(copy.deepcopy(self.project.notes))
            self.project.notes = self.future.pop()
            self.refresh()

    def mark_checked(self, value):
        row = self.list.currentRow()
        if value:
            self.reviewed.add(row)
        else:
            self.reviewed.discard(row)
        if 0 <= row < len(self.lines):
            start, end, text = self.lines[row]
            mark = ' [' + tr('review.checked') + ']' if value else ''
            self.list.item(row).setText(f'{row + 1}. {int(start // 60):02d}:{start % 60:05.2f}  {text}{mark}')

    def navigate(self, delta):
        self.list.setCurrentRow(max(0, min(len(self.lines) - 1, self.list.currentRow() + delta)))

    def preview_selected(self, identifier):
        note = next((n for n in self.project.notes if n.id == identifier), None)
        if note and note.pitch_assigned:
            self.preview_tone(note.pitch)

    def preview_tone(self, pitch):
        if not self.playing:
            self.tones.play(pitch, .4)

    def seek(self, seconds):
        self.position = max(0, seconds)
        self.clock = time.monotonic()
        self.clock_position = self.position
        self.player.setPosition(round(max(0, self.position + self.offset) * 1000))
        self.sounding = None
        self.tones.stop()
        self.timeline.set_cursor(self.position)

    def set_mode(self):
        self.audio.setMuted(self.mode.currentData() == 'notes')
        self.tones.stop()
        self.sounding = None

    def speed_changed(self):
        self.player.setPlaybackRate(self.speed.currentData())
        if self.playing:
            self.seek(self.position)

    def toggle_play(self):
        if self.playing:
            self.stop()
        elif self.lines:
            if self.position >= self.end or self.position < self.start - .2:
                self.seek(max(0, self.start - .2))
            self.playing = True
            self.clock = time.monotonic()
            self.clock_position = self.position
            if not self.player.source().isEmpty():
                self.player.play()
            self.timer.start()
            self.play.setIcon(qta.icon('fa5s.pause', color='#cdd3d9'))

    def tick(self):
        if not self.playing:
            return
        rate = self.speed.currentData()
        self.position = (self.player.position() / 1000 - self.offset
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            else self.clock_position + (time.monotonic() - self.clock) * rate)
        if self.position >= self.end:
            if self.loop.isChecked():
                self.seek(max(0, self.start - .2))
                if not self.player.source().isEmpty():
                    self.player.play()
            else:
                self.stop()
            return
        self.timeline.set_cursor(self.position)
        note = next((n for n in self.view.ordered() if n.pitch_assigned and
                     n.time <= self.position < n.time + n.length), None)
        identity = (note.id, note.pitch) if note else None
        if identity != self.sounding:
            self.sounding = identity
            self.tones.stop()
            if note and self.mode.currentData() != 'recording':
                self.tones.play(note.pitch, max(.02, min(self.end, note.time + note.length) - self.position) / rate)

    def stop(self):
        self.playing = False
        self.timer.stop()
        self.player.pause()
        self.tones.stop()
        self.sounding = None
        self.play.setIcon(qta.icon('fa5s.play', color='#cdd3d9'))

    def media_error(self, *_):
        self.stop()
        self.status.setText(self.player.errorString())

    def done(self, result):
        self.stop()
        self.player.stop()
        self.player.setSource(QUrl())
        super().done(result)
