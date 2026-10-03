"""Resolve framework devices without confusing ROCm's CUDA API with NVIDIA."""


def resolve_device(requested, torch):
    hip = bool(getattr(torch.version, 'hip', None))
    gpu_available = torch.cuda.is_available()
    backend = 'amd' if hip else 'cuda'
    if requested == 'auto':
        if gpu_available:
            requested = backend
        elif torch.backends.mps.is_available():
            requested = 'mps'
        else:
            requested = 'cpu'
    warnings = []
    if requested in ('amd', 'cuda'):
        if gpu_available and requested == backend:
            return backend, 'cuda', torch.cuda.get_device_name(0), warnings
        warnings.append(f'{requested} unavailable in this AI runtime: CPU fallback')
    elif requested == 'mps':
        if torch.backends.mps.is_available():
            return 'mps', 'mps', 'Apple Metal', warnings
        warnings.append('Apple Metal unavailable: CPU fallback')
    elif requested != 'cpu':
        raise ValueError('Unsupported AI device')
    return 'cpu', 'cpu', '', warnings
