"""Opt-in beat settings and bounded, local tempo detection."""
import copy
from pathlib import Path
import subprocess
import tempfile

from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox,
    QComboBox, QCheckBox, QPushButton, QDialogButtonBox, QLabel, QHBoxLayout)
import qtawesome as qta
from studio.i18n import tr


class BeatDetection(QThread):
    ready = Signal(float, float, int)
    failed = Signal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)

    def run(self):
        try:
            from studio.media import ffmpeg_encoder
            from studio.beat_grid import detect_beats
            import soundfile as sf
            source = self.project.audio_path or self.project.video_path
            if not Path(source).is_file():
                raise ValueError(tr('ai.no_media'))
            with tempfile.TemporaryDirectory(prefix='openlips-beats-') as folder:
                wave = Path(folder) / 'reference.wav'
                result = subprocess.run([ffmpeg_encoder(), '-nostdin', '-v', 'error', '-i', source,
                    '-t', '120', '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '22050', str(wave)],
                    capture_output=True, timeout=90,
                    creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name == 'nt' else 0)
                if result.returncode:
                    raise ValueError(result.stderr.decode('utf-8', 'replace')[-1500:])
                audio, rate = sf.read(wave, dtype='float32')
                if self.isInterruptionRequested():
                    return
                bpm, offset, count = detect_beats(audio, rate, self.project.bpm)
                if not self.isInterruptionRequested():
                    self.ready.emit(bpm, offset - self.project.reference_offset, count)
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))


class BeatGridDialog(QDialog):
    def __init__(self, project, parent=None, *, identifiers=None):
        super().__init__(parent)
        self.project = copy.deepcopy(project)
        self.worker = None
        self.pending_result = None
        self.identifiers = {n.id for n in project.notes} if identifiers is None else set(identifiers)
        self.setWindowTitle(tr('beat.title'))
        self.resize(470, 340)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.bpm = QDoubleSpinBox()
        self.bpm.setRange(1, 1000)
        self.bpm.setDecimals(2)
        self.bpm.setValue(project.bpm)
        self.offset = QDoubleSpinBox()
        self.offset.setRange(-86400, 86400)
        self.offset.setDecimals(3)
        self.offset.setSingleStep(.01)
        self.offset.setSuffix(' s')
        self.offset.setValue(project.beat_offset)
        self.division = QComboBox()
        for text, value in [('1/4', 1), ('1/8', 2), ('1/16', 4), ('1/8 '+tr('beat.triplet'), 3),
                            ('1/16 '+tr('beat.triplet'), 6), ('1/32', 8)]:
            self.division.addItem(text, value)
        self.division.setCurrentIndex(self.division.findData(project.beat_division))
        self.snap = QCheckBox(tr('beat.snap'))
        self.snap.setChecked(project.beat_snap)
        self.ticks = QCheckBox(tr('beat.ticks'))
        self.ticks.setChecked(project.beat_ticks)
        self.quantize = QCheckBox(tr('beat.quantize'))
        self.cut = QCheckBox(tr('beat.cut'))
        self.trim = QCheckBox(tr('beat.trim'))
        for widget in (self.quantize, self.cut, self.trim):
            widget.setEnabled(bool(self.identifiers))
        for title, widget in [('BPM', self.bpm), (tr('beat.offset'), self.offset),
                              (tr('beat.division'), self.division), ('', self.snap), ('', self.ticks),
                              ('', self.quantize), ('', self.cut), ('', self.trim)]:
            form.addRow(title, widget)
        root.addLayout(form)
        row = QHBoxLayout()
        self.detect = QPushButton(qta.icon('fa5s.search', color='#cdd3d9'), tr('beat.detect'))
        self.detect.clicked.connect(self.detect_tempo)
        row.addWidget(self.detect)
        for text, factor in [('÷2', .5), ('×2', 2)]:
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, f=factor: self.bpm.setValue(self.bpm.value() * f))
            row.addWidget(button)
        root.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('Uebernehmen'))
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Abbrechen'))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def detect_tempo(self):
        if self.worker and self.worker.isRunning():
            return
        self.worker = BeatDetection(self.project, self)
        self.worker.ready.connect(self.detected)
        self.worker.failed.connect(self.status.setText)
        self.worker.finished.connect(self.detection_finished)
        self.detect.setEnabled(False)
        self.status.setText(tr('beat.detecting'))
        self.worker.start()

    def detected(self, bpm, offset, count):
        self.bpm.setValue(bpm)
        self.offset.setValue(offset % (60 / bpm))
        self.status.setText(tr('beat.detected', count=count))

    def detection_finished(self):
        self.detect.setEnabled(True)
        if self.pending_result is not None:
            self.done(self.pending_result)

    def accept(self):
        self.project.bpm = self.bpm.value()
        self.project.beat_offset = self.offset.value()
        self.project.beat_division = self.division.currentData()
        self.project.beat_enabled = True
        self.project.beat_snap = self.snap.isChecked()
        self.project.beat_ticks = self.ticks.isChecked()
        from studio.beat_grid import quantize_notes, cut_notes, trim_overlaps
        candidate = copy.deepcopy(self.project)
        try:
            if self.quantize.isChecked():
                quantize_notes(candidate, self.identifiers)
            if self.trim.isChecked():
                trim_overlaps(candidate, self.identifiers)
            if self.cut.isChecked():
                cut_notes(candidate, self.identifiers)
            candidate.validate()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.project = candidate
        super().accept()

    def done(self, result):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.pending_result = result
            self.status.setText(tr('beat.stopping'))
            return
        super().done(result)


def copy_grid(source, target):
    for name in ('bpm', 'beat_offset', 'beat_division', 'beat_enabled', 'beat_snap', 'beat_ticks'):
        setattr(target, name, getattr(source, name))


class GridMetronome(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        from studio.beat_grid import BeatClock
        from studio.tone_preview import TonePreview
        self.clock = BeatClock()
        self.sound = TonePreview(self)
        self.sound.set_volume(.35)

    def tick(self, project, position):
        pitch = self.clock.tick(project, position)
        if pitch is not None:
            self.sound.play(pitch, .025)

    def stop(self):
        self.clock.reset()
        self.sound.stop()
