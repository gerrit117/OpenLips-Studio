from types import SimpleNamespace
import pytest
from tools.ai_devices import resolve_device
from tools.ai_transcription import transcribe_with_fallback


def framework(hip=None, available=False, metal=False):
    return SimpleNamespace(version=SimpleNamespace(hip=hip),
        cuda=SimpleNamespace(is_available=lambda: available, get_device_name=lambda i: 'Test GPU'),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: metal)))


@pytest.mark.parametrize('mode,hip,available,metal,expected', [
    ('auto', '7.2', True, False, ('amd', 'cuda')),
    ('auto', None, True, False, ('cuda', 'cuda')),
    ('auto', None, False, True, ('mps', 'mps')),
    ('auto', None, False, False, ('cpu', 'cpu')),
    ('cpu', '7.2', True, False, ('cpu', 'cpu'))])
def test_device_detection(mode, hip, available, metal, expected):
    assert resolve_device(mode, framework(hip, available, metal))[:2] == expected


@pytest.mark.parametrize('mode,hip', [('cuda', '7.2'), ('amd', None)])
def test_never_treat_rocm_as_nvidia(mode, hip):
    result = resolve_device(mode, framework(hip, True))
    assert result[:2] == ('cpu', 'cpu') and result[3]


def test_amd_transcription_failure_retries_cpu(monkeypatch):
    calls, progress = [], []
    def run(*args, backend, **kwargs):
        calls.append(backend)
        if backend == 'amd':
            raise RuntimeError('unsupported kernel')
        return [], 'en', 'faster-whisper', 'cpu'
    monkeypatch.setattr('tools.ai_transcription.transcribe_once', run)
    result = transcribe_with_fallback(backend='amd', progress=lambda *a, **k: progress.append(k))
    assert calls == ['amd', 'pytorch-cpu']
    assert result[-1] and progress[0]['device'] == 'cpu'


def test_cpu_failure_is_not_masked(monkeypatch):
    def fail(*a, **k):
        raise RuntimeError('bad model')
    monkeypatch.setattr('tools.ai_transcription.transcribe_once', fail)
    with pytest.raises(RuntimeError):
        transcribe_with_fallback(backend='cpu', progress=lambda *a, **k: None)
