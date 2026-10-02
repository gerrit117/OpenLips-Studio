"""Optional bounded CTC word alignment; no timing interpolation on failures."""
import numpy as np
from studio.ai_alignment import alignment_tokens
from studio.ai_chart import WordSpan


def align_windows(windows, audio, rate, cache, language='en', threads=4, progress=None):
    import torch
    import torchaudio
    from torchaudio.functional import forced_align, merge_tokens, resample
    names = {'en': 'WAV2VEC2_ASR_BASE_960H', 'de': 'VOXPOPULI_ASR_BASE_10K_DE'}
    if language not in names:
        raise ValueError('Known-lyric alignment currently supports explicit English or German only')
    torch.set_num_threads(threads)
    bundle = getattr(torchaudio.pipelines, names[language])
    (cache / 'alignment').mkdir(parents=True, exist_ok=True)
    model = bundle.get_model(dl_kwargs={'model_dir': str(cache / 'alignment')}).eval()
    labels = bundle.get_labels()
    waveform = torch.from_numpy(np.asarray(audio.mean(axis=1), dtype=np.float32))
    waveform = resample(waveform, rate, bundle.sample_rate)
    words, warnings = [], ['CTC word alignment is estimated, not phonetic syllable alignment; review sung vowels and repeated words.']
    for window in windows:
        if window.end - window.start > 60:
            warnings.append(f'Alignment window at {window.start:.3f}s exceeds 60 seconds; not interpolated')
            continue
        try:
            tokens, groups, notices = alignment_tokens(window.text, labels)
            start = int(window.start * bundle.sample_rate)
            stop = min(len(waveform), int(window.end * bundle.sample_rate))
            if stop - start < 400:
                raise ValueError('Window is too short for acoustic model')
            with torch.inference_mode():
                emission, _ = model(waveform[start:stop][None])
                log_probs = torch.log_softmax(emission, dim=-1)
                targets = torch.tensor([tokens], dtype=torch.int64)
                path, scores = forced_align(log_probs, targets, blank=0)
                spans = merge_tokens(path[0], scores[0].exp())
            if len(spans) != len(tokens):
                raise ValueError('Alignment did not resolve every supplied character')
            frame_seconds = (stop - start) / bundle.sample_rate / emission.shape[1]
            for index, (text, first, last) in enumerate(groups):
                begin = window.start + spans[first].start * frame_seconds
                end = window.start + spans[last - 1].end * frame_seconds
                confidence = sum(float(s.score) for s in spans[first:last]) / (last - first)
                if end > begin:
                    words.append(WordSpan(begin, min(end, window.end), text,
                                          window.phrase_end and index == len(groups) - 1, confidence))
            warnings.extend(notices)
        except (ValueError, RuntimeError) as exc:
            warnings.append(f'Unaligned window at {window.start:.3f}s: {exc}; no invented word times')
        if progress:
            progress('align', seconds=window.end, device='cpu')
    return words, warnings, names[language]
