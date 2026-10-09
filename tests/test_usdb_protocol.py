import importlib.util
from pathlib import Path


def test_current_usdb_service_advertises_native_batch_operation():
    spec = importlib.util.spec_from_file_location('usdb_service_test',
        Path(__file__).resolve().parents[1] / 'plugins/usdb_downloader/service.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    service = object.__new__(module.Service)
    capabilities = service.handle({'operation': 'capabilities'})
    assert capabilities['protocol'] == 2
    assert 'download_batch' in capabilities['operations']
