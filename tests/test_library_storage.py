"""Host-mounted directories need write access, not permission-changing rights."""
from contextlib import nullcontext
from unittest.mock import patch

import pytest

from library_server.app import main


def test_startup_does_not_chmod_host_mount(tmp_path):
    arguments = ['--config', str(tmp_path / 'server.json'),
                 '--library', str(tmp_path / 'library')]
    with patch('library_server.app.os.chmod', side_effect=PermissionError('Host-owned mount')), \
         patch('library_server.app.server_lock', return_value=nullcontext()), \
         patch('library_server.app.serve', return_value=0) as serve:
        assert main(arguments) == 0
        assert main(arguments) == 0
        assert serve.call_count == 2


def test_permission_failure_explains_storage_access(tmp_path, capsys):
    config = tmp_path / 'server.json'
    with patch('library_server.app.create_config',
               side_effect=PermissionError(13, 'Permission denied', str(config))), \
         patch('library_server.app.serve') as serve:
        with pytest.raises(SystemExit) as error:
            main(['--config', str(config)])
        assert error.value.code == 2
        serve.assert_not_called()
    message = capsys.readouterr().err
    assert 'Mount the data directory read/write' in message
    assert 'UID/GID' in message
    assert 'Traceback' not in message
