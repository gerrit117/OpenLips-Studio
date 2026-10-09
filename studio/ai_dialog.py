"""Built-in analysis/review; heavy inference is isolated from the Qt process."""
from pathlib import Path
import os
import sys
import tempfile

from PySide6.QtCore import QProcess, QSettings, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QComboBox, QCheckBox, QSpinBox,
    QTableWidget, QTableWidgetItem, QPlainTextEdit, QMessageBox, QDialogButtonBox, QProgressBar, QLabel)
import qtawesome as qta
from studio.i18n import tr, language
from studio.model import load_project, pitch_name
from studio.media import ffmpeg_encoder


class AiChartDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ai.title'))
        available = self.screen().availableGeometry()
        self.resize(min(960, available.width() - 60), min(780, available.height() - 60))
        self.result_project, self.worker, self.downloader = None, None, None
        self.reference_project = project
        self.cpu_retry, self.cancelled = False, False
        self.project_audio = project.audio_path
        self.folder = tempfile.TemporaryDirectory(prefix='openlips-ai-review-')
        self.output = Path(self.folder.name) / 'draft.olp'
        self.log_path = Path(self.folder.name) / 'progress.jsonl'
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.input = QLineEdit(project.audio_path or project.video_path)
        self.lrc = QLineEdit()
        if project.lyric_reference and project.lyric_reference.get('raw'):
            reference = Path(self.folder.name) / 'reference.lrc'
            reference.write_text(project.lyric_reference['raw'], encoding='utf-8')
            self.lrc.setText(str(reference))
        self.runtime = QLineEdit(QSettings().value('ai/python', '', str))
        from studio.ai_runtime import installed_engine
        if self.runtime.text() and not Path(self.runtime.text()).is_file():
            self.runtime.clear()
        cached = installed_engine()
        engine = Path(sys.executable).parent / 'ai' / ('OpenLipsAI.exe' if os.name == 'nt' else 'OpenLipsAI')
        local = Path(__file__).resolve().parents[1] / 'private/runtime/ai-chart-env/Scripts/python.exe'
        if not self.runtime.text():
            if cached:
                self.runtime.setText(cached)
            elif engine.is_file():
                self.runtime.setText(str(engine))
            elif local.is_file():
                self.runtime.setText(str(local))
        for label, widget, filter in [(tr('ai.media'), self.input, '*'), ('LRC', self.lrc, '*.lrc')]:
            row = QHBoxLayout()
            row.addWidget(widget)
            browse = QPushButton(qta.icon('fa5s.folder-open', color='#cdd3d9'), '')
            browse.setToolTip(tr('Projekt oeffnen'))
            browse.clicked.connect(lambda checked=False, w=widget, f=filter: self.browse(w, f))
            row.addWidget(browse)
            form.addRow(label, row)
        self.separate = QCheckBox(tr('ai.separate'))
        self.transcribe = QCheckBox(tr('ai.transcribe'))
        self.word_notes = QCheckBox(tr('ai.word_notes'))
        self.word_notes.setChecked(False)
        self.align_lrc = QCheckBox(tr('ai.align_lrc'))
        self.model = QComboBox()
        self.model.addItems(['tiny', 'base', 'small', 'medium', 'large-v3'])
        self.model.setCurrentText('base')
        self.language = QComboBox()
        for label, value in [(tr('ai.auto'), ''), ('English', 'en'), ('Deutsch', 'de')]:
            self.language.addItem(label, value)
        self.language.setCurrentIndex(self.language.findData('de' if language() == 'de' else 'en'))
        if self.lrc.text():
            from studio.lrc import read_lrc
            self.align_lrc.setChecked(all(not cue.words for cue in read_lrc(self.lrc.text()).cues))
        self.device = QComboBox()
        for label, value in [(tr('ai.auto'), 'auto'), ('CPU', 'cpu'), ('AMD Radeon (ROCm)', 'amd'),
                             ('NVIDIA CUDA', 'cuda'), ('Apple Metal', 'mps')]:
            self.device.addItem(label, value)
        self.threads = QSpinBox()
        self.threads.setRange(1, 64)
        self.threads.setValue(4)
        for label, widget in [('', self.separate), ('', self.transcribe), ('', self.align_lrc), ('', self.word_notes), (tr('ai.asr_model'), self.model),
                (tr('ai.language'), self.language), (tr('ai.device'), self.device), (tr('ai.threads'), self.threads)]:
            form.addRow(label, widget)
        root.addLayout(form)
        controls = QHBoxLayout()
        self.run = QPushButton(qta.icon('fa5s.play', color='#cdd3d9'), tr('ai.analyze'))
        self.cancel_run = QPushButton(qta.icon('fa5s.stop', color='#cdd3d9'), tr('Stopp'))
        self.cancel_run.setEnabled(False)
        controls.addWidget(self.run)
        controls.addWidget(self.cancel_run)
        controls.addStretch()
        root.addLayout(controls)
        self.download_status = QLabel()
        root.addWidget(self.download_status)
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        root.addWidget(self.download_progress)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Start (s)', tr('Laenge'), tr('Tonname'), 'Text'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(200)
        self.log.setMaximumHeight(130)
        root.addWidget(self.log)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('ai.cancel'))
        self.accept_button = buttons.addButton(tr('review.title'), QDialogButtonBox.ButtonRole.AcceptRole)
        self.accept_button.setEnabled(False)
        buttons.accepted.connect(self.review_result)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.run.clicked.connect(self.start)
        self.cancel_run.clicked.connect(self.stop)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.read_log)

    def browse(self, widget, filter):
        path, _ = QFileDialog.getOpenFileName(self, tr('Projekt oeffnen'), widget.text(), filter)
        if path:
            widget.setText(path)
            if widget is self.lrc:
                try:
                    from studio.lrc import read_lrc
                    self.align_lrc.setChecked(all(not cue.words for cue in read_lrc(path).cues))
                except (ValueError, OSError):
                    pass

    def review_result(self):
        if not self.result_project:
            return
        from studio.guided_review import GuidedReviewDialog, review_draft
        candidate = review_draft(self.result_project, self.reference_project)
        audio = Path(self.folder.name) / 'reference.wav'
        dialog = GuidedReviewDialog(candidate, self, audio_path=str(audio) if audio.is_file() else None)
        if dialog.exec():
            self.result_project.notes = dialog.project.notes
            self.accept()

    def start(self):
        if self.downloader and self.downloader.isRunning():
            return
        if not Path(self.input.text()).is_file():
            QMessageBox.warning(self, tr('ai.title'), tr('ai.no_media'))
            return
        runtime = self.runtime.text().strip()
        from studio.ai_runtime import amd_engine, has_amd_gpu
        wants_amd = self.device.currentData() == 'amd' or (
            self.device.currentData() == 'auto' and has_amd_gpu())
        if wants_amd:
            accelerated = amd_engine()
            if accelerated:
                runtime = accelerated
                self.runtime.setText(runtime)
            else:
                runtime = ''
        if self.align_lrc.isChecked() and (not self.lrc.text().strip() or not self.language.currentData()):
            QMessageBox.warning(self, tr('ai.title'), tr('ai.need_lrc'))
            return
        heavy = self.separate.isChecked() or self.align_lrc.isChecked() or (self.transcribe.isChecked() and not self.lrc.text().strip())
        if heavy and (not runtime or not Path(runtime).is_file()):
            self.download_engine(flavor='amd' if wants_amd else 'cpu')
            return
        try:
            from studio.media_source import analysis_audio_source
            source = analysis_audio_source(self.input.text(), self.project_audio)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, tr('ai.title'), str(error))
            return
        if source != self.input.text():
            self.input.setText(source)
            self.download_status.setText(tr('ai.separate_audio', name=Path(source).name))
        QSettings().setValue('ai/python', runtime)
        self.result_project = None
        self.accept_button.setEnabled(False)
        self.table.setRowCount(0)
        self.log.clear()
        for path in (self.output, self.log_path, self.output.with_suffix('.analysis.json')):
            if path.exists():
                path.unlink()
        args = [self.input.text(), '--out', str(self.output), '--progress-file', str(self.log_path),
                '--work-dir', self.folder.name,
                '--ffmpeg', ffmpeg_encoder(), '--model', self.model.currentText(),
                '--device', self.device.currentData(), '--threads', str(self.threads.value())]
        if self.language.currentData():
            args += ['--language', self.language.currentData()]
        if self.separate.isChecked():
            args += ['--separate']
        if self.word_notes.isChecked():
            args += ['--word-notes']
        if self.lrc.text().strip():
            args += ['--lrc', self.lrc.text().strip()]
            if self.align_lrc.isChecked():
                args += ['--align-lrc']
        elif self.transcribe.isChecked():
            args += ['--transcribe']
        if runtime and Path(runtime).stem.casefold() == 'openlipsai':
            program = runtime
        elif runtime or not getattr(sys, 'frozen', False):
            program, args = runtime or sys.executable, ['-m', 'tools.create_ai_chart', *args]
        else:
            program, args = sys.executable, ['--ai-worker', *args]
        self.worker = QProcess(self)
        self.cpu_retry, self.cancelled = False, False
        self.active_program, self.active_args = program, list(args)
        if os.name != 'nt':
            parameters = QProcess.UnixProcessParameters()
            parameters.flags = QProcess.UnixProcessFlag.CreateNewSession
            self.worker.setUnixProcessParameters(parameters)
        root = Path(__file__).resolve().parents[1]
        if runtime and Path(runtime).stem.casefold() != 'openlipsai' and getattr(sys, 'frozen', False):
            root = Path(sys._MEIPASS) / 'ai_backend'
        self.worker.setWorkingDirectory(str(root))
        self.worker.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.worker.readyReadStandardOutput.connect(self.worker_output)
        self.worker.finished.connect(self.worker_finished)
        self.worker.errorOccurred.connect(self.failed_start)
        self.run.setEnabled(False)
        self.cancel_run.setEnabled(True)
        self.worker.start(program, args)
        self.timer.start()

    def download_engine(self, flavor='cpu'):
        from studio.ai_runtime import EngineDownload
        self.downloader = EngineDownload(self, flavor=flavor)
        self.download_result = None
        self.run.setEnabled(False)
        self.cancel_run.setEnabled(True)
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setVisible(True)
        self.download_status.setText(tr('ai.downloading'))
        self.downloader.progress.connect(self.download_update)
        self.downloader.ready.connect(self.engine_ready)
        self.downloader.failed.connect(self.download_failed)
        self.downloader.finished.connect(self.finish_engine_download)
        self.downloader.start()

    def download_update(self, value, message):
        self.download_progress.setValue(value)
        self.download_status.setText(tr('ai.downloading') + ' — ' + message)

    def engine_ready(self, path):
        self.download_result = path
        self.runtime.setText(path)
        QSettings().setValue('ai/python', path)
        fallback = self.downloader.flavor == 'amd' and self.downloader.actual_flavor == 'cpu'
        if fallback:
            self.device.setCurrentIndex(self.device.findData('cpu'))
        self.download_status.setText(tr('ai.amd_pending_cpu') if fallback else tr('ai.engine_ready'))
        self.download_progress.setVisible(False)
        # Queue analysis after the installer thread has finished its cleanup.

    def finish_engine_download(self):
        if self.download_result and not self.downloader.isInterruptionRequested():
            self.start()
        else:
            self.run.setEnabled(True)
            self.cancel_run.setEnabled(False)

    def download_failed(self, message):
        self.download_status.setText(message)
        self.download_progress.setVisible(False)
        self.run.setEnabled(True)
        self.cancel_run.setEnabled(False)

    def failed_start(self, error):
        self.log.appendPlainText(self.worker.errorString())
        if self.worker.state() == QProcess.ProcessState.NotRunning:
            self.timer.stop()
            self.run.setEnabled(True)
            self.cancel_run.setEnabled(False)

    def worker_output(self):
        output = bytes(self.worker.readAllStandardOutput()).decode('utf-8', 'replace')
        if output.strip():
            self.log.appendPlainText(output[-4000:])

    def read_log(self):
        if self.log_path.exists():
            self.log.setPlainText(self.log_path.read_text(encoding='utf-8')[-12000:])

    def stop(self):
        self.cancelled = True
        if self.downloader and self.downloader.isRunning():
            self.downloader.requestInterruption()
            self.download_status.setText(tr('ai.download_stopping'))
            return
        if self.worker and self.worker.state() != QProcess.ProcessState.NotRunning:
            if os.name == 'nt':
                QProcess.execute('taskkill', ['/PID', str(self.worker.processId()), '/T', '/F'])
            else:
                import signal
                try:
                    os.killpg(self.worker.processId(), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.worker.waitForFinished(3000)

    def worker_finished(self, code, status):
        self.timer.stop()
        self.read_log()
        if (status == QProcess.ExitStatus.CrashExit and not self.cancelled
                and not self.cpu_retry and hasattr(self, 'active_args')):
            index = self.active_args.index('--device') + 1
            if self.active_args[index] != 'cpu':
                self.cpu_retry = True
                self.active_args[index] = 'cpu'
                for path in (self.output, self.log_path, self.output.with_suffix('.analysis.json')):
                    path.unlink(missing_ok=True)
                self.log.appendPlainText(tr('ai.cpu_retry'))
                self.download_status.setText(tr('ai.cpu_retry'))
                self.worker.start(self.active_program, self.active_args)
                self.timer.start()
                return
        self.run.setEnabled(True)
        self.cancel_run.setEnabled(False)
        if code or status != QProcess.ExitStatus.NormalExit or not self.output.is_file():
            self.log.appendPlainText(tr('ai.failed'))
            return
        try:
            result = load_project(self.output)
        except (ValueError, OSError) as exc:
            self.log.appendPlainText(str(exc))
            return
        self.result_project = result
        self.table.setRowCount(len(result.notes))
        for row, note in enumerate(result.ordered()):
            for column, value in enumerate((f'{note.time:.3f}', f'{note.length:.3f}', pitch_name(note.pitch), note.text)):
                self.table.setItem(row, column, QTableWidgetItem(value))
        for warning in result.warnings[:30]:
            self.log.appendPlainText(warning)
        self.accept_button.setEnabled(bool(result.notes))

    def done(self, result):
        if self.downloader and self.downloader.isRunning():
            self.stop()
            return
        self.stop()
        self.timer.stop()
        self.folder.cleanup()
        super().done(result)

    def closeEvent(self, event):
        if self.downloader and self.downloader.isRunning():
            self.stop()
            event.ignore()
            return
        self.stop()
        super().closeEvent(event)
