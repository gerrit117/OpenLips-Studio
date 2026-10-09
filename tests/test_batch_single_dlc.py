"""Single-song batch selection and sequential exports using synthetic projects."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from studio.batch_dlc_dialog import SingleDlcWorker
from studio.model import EditorNote, StudioProject
from studio.ultrastar_batch_dialog import UltraStarBatchDialog


def projects(count):
    return [StudioProject(title=f'Song {i}', artist='Test', notes=[EditorNote(1,1,60,'Test')]) for i in range(count)]


def test_singles_selection_is_not_limited_to_pack_size():
    app = QApplication.instance() or QApplication([])
    dialog = UltraStarBatchDialog()
    dialog.receive([(f'/demo/{i}.txt',p) for i,p in enumerate(projects(17))], [])
    dialog.update_buttons()
    assert not dialog.export_button.isEnabled()
    dialog.export_mode.setCurrentIndex(dialog.export_mode.findData('singles'))
    assert dialog.export_button.isEnabled()
    assert dialog.name.isHidden()
    dialog.close()
    app.processEvents()


def test_single_batch_builds_separately_and_continues_after_error(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('studio.library_page.configured_library', lambda: None)
    calls=[]
    def build(songs, output, progress, **options):
        assert len(songs)==1 and options==dict(optimize_pages=True)
        calls.append(songs[0].title)
        if songs[0].title=='Song 1':
            raise ValueError('synthetic missing media')
        return dict(output_path=str(output / (songs[0].title+'.LIVE')))
    monkeypatch.setattr('studio.dlc_pack.build_projects_dlc', build)
    worker=SingleDlcWorker(projects(3),tmp_path)
    results=[]
    worker.completed.connect(lambda outputs,errors:results.append((outputs,errors)))
    worker.run()
    assert calls==['Song 0','Song 1','Song 2']
    assert len(results[0][0])==2 and len(results[0][1])==1
    app.processEvents()


def test_cancel_between_songs_keeps_completed_outputs(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('studio.library_page.configured_library', lambda: None)
    worker=SingleDlcWorker(projects(3),tmp_path)
    cancelled=[False]
    monkeypatch.setattr(worker,'isInterruptionRequested',lambda:cancelled[0])
    def build(songs,output,progress,**options):
        cancelled[0]=True
        return dict(output_path=str(output/'completed.LIVE'))
    monkeypatch.setattr('studio.dlc_pack.build_projects_dlc',build)
    results=[]
    worker.completed.connect(lambda outputs,errors:results.append(outputs))
    worker.run()
    assert len(results[0])==1
    app.processEvents()
