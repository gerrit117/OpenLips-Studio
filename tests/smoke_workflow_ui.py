"""Render or interact with the actual workflow using isolated, synthetic media."""
import argparse
from pathlib import Path
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interactive', action='store_true')
    parser.add_argument('--width', type=int, default=1440)
    parser.add_argument('--height', type=int, default=920)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    import numpy as np
    from studio.model import StudioProject, EditorNote
    rate = 22050
    seconds = np.arange(rate*40)/rate
    audio = .05*np.sin(2*np.pi*261.63*seconds)+.025*np.sin(2*np.pi*329.63*seconds)
    audio *= .65+.35*np.sin(2*np.pi*133/60*seconds)**8
    media = args.output/'synthetic.wav'
    with wave.open(str(media), 'wb') as stream:
        stream.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        stream.writeframes((audio*32767).astype('<i2').tobytes())
    text = 'Unter Lichtern zieh ich weiter\nbis der Morgen uns erreicht\n\nJeder Schritt wird etwas leichter\nwenn der letzte Schatten weicht'
    project = StudioProject(title='Neonregen', artist='OpenLips Demo', bpm=133,
        key_signature='G#', audio_path=str(media.resolve()), draft_lyrics=text,
        beat_enabled=True, beat_division=2, genre='Pop', year='2026')
    syllables = [('Un', 62, .5, False), ('ter', 62, .4, True), ('Lich', 66, .5, False), ('tern', 66, .35, True),
                 ('zieh', 65, .35, True), ('ich', 64, .35, True), ('weiter', 65, .6, False),
                 ('~', 66, .45, False), ('~', 67, .6, True), ('bis', 64, .4, True),
                 ('der', 63, .4, True), ('Mor', 62, .5, False), ('gen', 61, .55, True),
                 ('uns', 62, .35, True), ('erreicht', 64, .7, True)]
    position = 16.
    for fragment, pitch, length, end_word in syllables:
        project.notes.append(EditorNote(position, length, pitch, fragment, end_word))
        position += length+.05
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(args.output/'settings'))
    app = QApplication([])
    from studio.i18n import set_language
    from studio.fonts import use_system_font
    from studio.style import STUDIO_STYLE
    from studio.app import StudioWindow
    set_language('de', persist=False)
    use_system_font(app)
    app.setStyle('Fusion')
    app.setStyleSheet(STUDIO_STYLE)
    window = StudioWindow()
    window.resize(args.width, args.height)
    window.replace_project(project)
    window.workflow.last_media = (project.audio_path, project.video_path)
    window.workflow.waveform.samples = [float(np.max(np.abs(chunk))) for chunk in np.array_split(audio, 1200)]
    window.workflow.waveform.duration = 40
    window.editor_waveform.samples = window.workflow.waveform.samples
    window.editor_waveform.duration = 40
    window.editor_waveform.show()
    window.show()
    steps = iter([(0, 'source'), (1, 'prepare'), (2, 'lyrics'), (3, 'editor'), (4, 'export')])

    def capture():
        try:
            step, name = next(steps)
            window.workflow.go(step)
            if step == 3:
                window.timeline.follow = False
                window.timeline.origin = 16
                window.position = 19.2
                window.timeline.selected_ids = {project.notes[6].id}
                window.select_note(project.notes[6].id)
                window.update_cursor()
            app.processEvents()
            assert window.grab().save(str(args.output/f'{name}-{args.width}.png'))
            QTimer.singleShot(150, capture)
        except StopIteration:
            window.workflow.go(3)
            window.dirty = False
            if not args.interactive:
                window.close()
                app.quit()
    QTimer.singleShot(300, capture)
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
