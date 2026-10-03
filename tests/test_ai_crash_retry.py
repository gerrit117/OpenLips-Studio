from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QProcess

from studio.ai_dialog import AiChartDialog


@pytest.mark.parametrize('cancelled,already_retried,device,retries', [
    (False, False, 'amd', True),
    (False, True, 'amd', False),
    (True, False, 'amd', False),
    (False, False, 'cpu', False),
])
def test_native_crash_retries_cpu_once(tmp_path, cancelled, already_retried, device, retries):
    dialog = SimpleNamespace(
        timer=Mock(), read_log=Mock(), cancelled=cancelled, cpu_retry=already_retried,
        active_args=['input.wav', '--device', device], active_program='OpenLipsAI.exe',
        output=tmp_path / 'draft.olp', log_path=tmp_path / 'log.txt',
        log=Mock(), download_status=Mock(), worker=Mock(), run=Mock(), cancel_run=Mock(),
    )
    AiChartDialog.worker_finished(dialog, 1, QProcess.ExitStatus.CrashExit)
    if retries:
        dialog.worker.start.assert_called_once_with('OpenLipsAI.exe', ['input.wav', '--device', 'cpu'])
        assert dialog.cpu_retry
    else:
        dialog.worker.start.assert_not_called()
