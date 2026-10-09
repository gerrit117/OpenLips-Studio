"""End-to-end source/frozen GUI smoke test using only original generated tones."""
import json
from pathlib import Path
import time
import sys
import os
import math
import struct
import wave

from PySide6.QtCore import QSettings, QTimer

from studio.model import StudioProject
from studio.plugin_dialog import PluginDialog


def synthetic_audio(path):
    rate = 22050
    samples = []
    for pitch in (60, 64, 67, 72):
        frequency = 440 * 2 ** ((pitch - 69) / 12)
        for index in range(rate):
            t = index / rate
            envelope = min(1, t / .03, (1 - t) / .05)
            value = sum(math.sin(2 * math.pi * frequency * h * t) / h for h in range(1, 5))
            samples.append(round(7000 * envelope * value))
        samples.extend([0] * (rate // 5))
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes(struct.pack('<' + 'h' * len(samples), *samples))


def run(app, window, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = output / 'synthetic.wav'
    synthetic_audio(source)
    window.replace_project(StudioProject(title='Plugin Test', artist='OpenLips Studio'))
    settings = QSettings(str(output / 'settings.ini'), QSettings.Format.IniFormat)
    from studio.plugin_package import install_package
    package = os.environ.get('OPENLIPS_SMOKE_PLUGIN')
    if not package:
        raise ValueError('Set OPENLIPS_SMOKE_PLUGIN to the platform .opl for this integration test')
    folder = install_package(package, output / 'installed-plugins')
    settings.setValue('plugins/folders', [str(folder)])
    settings.setValue('plugins/enabled', ['spotify-basic-pitch'])
    dialog = PluginDialog(window.project, window, settings)
    dialog.input.setText(str(source))
    dialog.accepted_project.connect(window.apply_plugin_notes)
    window.smoke_dialog = dialog
    dialog.show()
    dialog.run_plugin()
    started = time.monotonic()
    timer = QTimer(window)
    timer.setInterval(100)
    window.smoke_timer = timer

    def check():
        if time.monotonic() - started > 180:
            dialog.cancel()
            (output / 'error.txt').write_text('Plugin smoke timed out', encoding='utf-8')
            # Wait for process shutdown rather than destroying an active worker.
            if not dialog.busy():
                app.exit(1)
            return
        if dialog.busy():
            return
        timer.stop()
        (output / 'analysis.log').write_text(dialog.log.toPlainText(), encoding='utf-8')
        try:
            assert dialog.result is not None, dialog.status.text()
            assert {60, 64, 67}.issubset({note.pitch for note in dialog.result.notes})
            assert dialog.apply_button.isEnabled()
            assert dialog.export_button.isEnabled()
            dialog.input.setText(source.name)
            assert dialog.grab().save(str(output / 'plugins.png'))
            def accept_review():
                from studio.guided_review import GuidedReviewDialog
                review = app.activeModalWidget()
                if isinstance(review, GuidedReviewDialog):
                    assert review.grab().save(str(output / 'guided-review.png'))
                    review.accept()
            QTimer.singleShot(100, accept_review)
            dialog.apply_result()
            assert window.project.notes
            assert window.project.title == 'Plugin Test'
            assert window.project.audio_path == str(source)
            assert not window.windowIcon().isNull()
            window.undo()
            assert not window.project.notes
            window.redo()
            assert window.project.notes
            app.processEvents()
            assert window.grab().save(str(output / 'editor.png'))
            (output / 'result.json').write_text(json.dumps(window.project.to_payload()), encoding='utf-8')
            app.exit(0)
        except Exception as error:
            (output / 'error.txt').write_text(str(error), encoding='utf-8')
            print(str(error), file=sys.stderr, flush=True)
            print(dialog.log.toPlainText(), file=sys.stderr, flush=True)
            app.exit(1)

    timer.timeout.connect(check)
    timer.start()
