"""Whisper adapters: ROCm uses PyTorch, never NVIDIA-only CTranslate2 kernels."""
import math
from pathlib import Path
from studio.ai_chart import WordSpan


def transcribe_once(wave, audio, rate, model_name, language, cache, backend, threads, progress):
    words = []
    import torch
    if backend == 'cpu' and getattr(torch.version, 'hip', None):
        backend = 'pytorch-cpu'
    if backend in ('amd', 'pytorch-cpu'):
        import numpy as np
        import whisper
        from scipy.signal import resample_poly
        mono = np.asarray(audio.mean(axis=1), dtype=np.float32)
        divisor = math.gcd(int(rate), 16000)
        mono = resample_poly(mono, 16000 // divisor, int(rate) // divisor).astype(np.float32)
        actual = 'amd' if backend == 'amd' else 'cpu'
        progress('transcribe', model=model_name, device=actual, backend='pytorch-whisper')
        model = whisper.load_model(model_name, device='cuda' if backend == 'amd' else 'cpu',
                                   download_root=str(Path(cache) / 'whisper-pytorch'))
        result = model.transcribe(mono, language=language or None, word_timestamps=True,
            condition_on_previous_text=False, fp16=backend == 'amd', verbose=None)
        segments = result['segments']
        detected = result['language']
        engine = 'pytorch-whisper'
    else:
        from faster_whisper import WhisperModel
        actual = 'cuda' if backend == 'cuda' else 'cpu'
        progress('transcribe', model=model_name, device=actual, backend='faster-whisper')
        model = WhisperModel(model_name, device=actual,
            compute_type='float16' if actual == 'cuda' else 'int8',
            download_root=str(Path(cache) / 'whisper'), cpu_threads=threads)
        generated, info = model.transcribe(str(wave), language=language or None,
            word_timestamps=True, condition_on_previous_text=False, vad_filter=False, beam_size=5)
        # Iterate inside the fallback boundary: CTranslate2 inference is lazy.
        segments = [dict(end=s.end, words=[dict(start=w.start, end=w.end,
            word=w.word, probability=w.probability) for w in s.words or ()]) for s in generated]
        detected, engine = info.language, 'faster-whisper'
    for segment in segments:
        valid = [w for w in segment.get('words', ()) if w['end'] > w['start'] and w['word'].strip()]
        for index, word in enumerate(valid):
            start = max(0.0, float(word['start']), words[-1].end if words else 0.0)
            if word['end'] > start:
                words.append(WordSpan(start, float(word['end']), word['word'].strip(),
                    index == len(valid) - 1, word.get('probability')))
        progress('transcribe', seconds=segment['end'], device=actual)
    return words, detected, engine, actual


def transcribe_with_fallback(*args, backend, **kwargs):
    try:
        return (*transcribe_once(*args, backend=backend, **kwargs), [])
    except (RuntimeError, ImportError) as error:
        if backend not in ('amd', 'cuda'):
            raise
        notice = f'{backend} transcription failed ({type(error).__name__}): retrying CPU'
        kwargs['progress']('fallback', message=notice, device='cpu')
        # ROCm and CTranslate2 ship different OpenMP runtimes on Windows.
        # Keep the AMD fallback in PyTorch rather than loading both together.
        fallback = 'pytorch-cpu' if backend == 'amd' else 'cpu'
        return (*transcribe_once(*args, backend=fallback, **kwargs), [notice])
