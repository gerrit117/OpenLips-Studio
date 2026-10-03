"""Isolated, CPU-first audio -> editable Studio project. Never touches game files."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from studio.ai_chart import PitchSpan, WordSpan, notes_from_analysis, words_from_lrc, word_error_rate
from studio.model import StudioProject, save_project


def progress(stage, **values):
    if sys.stdout:
        print(json.dumps(dict(stage=stage, **values), ensure_ascii=False), flush=True)


def separate(audio, rate, cache, device):
    import numpy as np
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    from demucs.audio import convert_audio
    # Model downloads are restricted to Demucs' built-in named model registry.
    torch.hub.set_dir(str(cache / 'torch'))
    model = get_model('htdemucs')
    waveform = torch.from_numpy(np.asarray(audio.T, dtype=np.float32))
    waveform = convert_audio(waveform, rate, model.samplerate, model.audio_channels)
    reference = waveform.mean(0)
    mean, std = reference.mean(), reference.std()
    if std < 1e-8:
        raise ValueError('Audio is silent')
    waveform = (waveform - mean) / std
    with torch.inference_mode():
        result = apply_model(model, waveform[None], device=device, shifts=0,
                             split=True, overlap=.25, progress=False)[0]
    vocals = result[model.sources.index('vocals')] * std + mean
    return vocals.cpu().numpy().T, model.samplerate


def analyze(args):
    import numpy as np
    import soundfile as sf
    from swift_f0 import SwiftF0, segment_notes
    started = time.monotonic()
    input_path = args.input.resolve(strict=True)
    report_path = args.out.with_suffix('.analysis.json')
    if args.out.resolve() == input_path or report_path.resolve() == input_path:
        raise ValueError('Output must not replace input media')
    if args.out.exists() or report_path.exists():
        raise FileExistsError('Output already exists; choose a new project path')
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    report = dict(format='openlips-ai-analysis', version=1, input=str(input_path),
                  requested_device=args.device, pitch_model='SwiftF0 0.3.0',
                  separation='htdemucs' if args.separate else 'none', warnings=[])
    ffmpeg = args.ffmpeg
    if not ffmpeg:
        bundled = Path(getattr(sys, '_MEIPASS', '')) / 'media' / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        if getattr(sys, 'frozen', False) and bundled.is_file():
            ffmpeg = str(bundled)
        else:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if not ffmpeg:
        raise ValueError('Bundled FFmpeg is unavailable')
    with tempfile.TemporaryDirectory(prefix='openlips-ai-', dir=args.work_dir) as directory:
        wav = Path(directory) / 'reference.wav'
        progress('decode')
        command = [ffmpeg, '-nostdin', '-v', 'error', '-i', str(input_path)]
        command += ['-t', str(args.duration or 1800.1)]
        command += ['-map', '0:a:0', '-vn', '-ac', '2', '-ar', '44100', str(wav)]
        decoded = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=7200,
                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if decoded.returncode:
            if b'matches no streams' in decoded.stderr:
                raise ValueError('This video has no audio track. Select the separate song audio file.')
            detail = decoded.stderr.decode('utf-8', errors='replace')[-1500:]
            raise ValueError('Audio decoding failed: ' + detail)
        audio, rate = sf.read(wav, dtype='float32', always_2d=True)
        if not len(audio) or len(audio) / rate > 1800:
            raise ValueError('Audio must contain between 0 and 1800 seconds')
        report['duration'] = len(audio) / rate
        device, backend = 'cpu', 'cpu'
        if args.separate or args.transcribe:
            import torch
            from tools.ai_devices import resolve_device
            torch.set_num_threads(args.threads)
            backend, device, gpu, notices = resolve_device(args.device, torch)
            report['warnings'].extend(notices)
            report['gpu_name'] = gpu
            progress('device', requested=args.device, backend=backend, gpu=gpu)
        if args.separate:
            progress('separate', model='htdemucs', device=backend)
            try:
                audio, rate = separate(audio, rate, cache, device)
            except RuntimeError:
                if device == 'cpu':
                    raise
                report['warnings'].append(f'{device} separation failed: retrying CPU')
                device = 'cpu'
                # Fresh model instance; no global torch.load overrides.
                audio, rate = sf.read(wav, dtype='float32', always_2d=True)
                audio, rate = separate(audio, rate, cache, 'cpu')
            sf.write(wav, audio, rate)
        report['separation_device'] = (backend if device != 'cpu' else 'cpu') if args.separate else 'not used'
        if args.device not in ('cpu', 'auto') and not args.separate and not args.transcribe:
            report['warnings'].append('Pitch and supplied-lyric alignment use CPU; requested accelerator is not used.')
        words = []
        if args.lrc:
            from studio.lrc import read_lrc
            document = read_lrc(args.lrc)
            words, warnings = words_from_lrc(document, report['duration'])
            report['warnings'].extend(warnings)
            report['word_source'] = 'user LRC anchors'
            if args.align_lrc:
                if not args.language:
                    raise ValueError('Select English or German for known-lyric alignment')
                from tools.align_lyrics import align_windows
                progress('align', language=args.language, device='cpu')
                words, notices, alignment_model = align_windows(words, audio, rate, cache,
                    language=args.language, threads=args.threads, progress=progress)
                report['warnings'].extend(notices)
                report['alignment_model'] = alignment_model
                report['alignment_device'] = 'cpu'
                report['word_source'] = 'supplied LRC text with estimated CTC word alignment'
                if not words:
                    raise ValueError('No supplied lyric windows could be aligned; input/project unchanged')
        elif args.transcribe:
            from tools.ai_transcription import transcribe_with_fallback
            report['asr_model'] = args.model
            words, language, engine, actual, notices = transcribe_with_fallback(
                wav, audio, rate, args.model, args.language, cache, threads=args.threads,
                progress=progress, backend=backend)
            report.update(language=language, asr_backend=engine, asr_device=actual)
            report['warnings'].extend(notices)
            report['word_source'] = 'Whisper estimated word timestamps (not forced alignment)'
        progress('pitch', model='SwiftF0', device='cpu')
        detector = SwiftF0(threads=args.threads)
        result = detector.detect(audio.mean(axis=1), rate, fmin=args.fmin, fmax=args.fmax)
        spans = []
        for note in segment_notes(result, pitch_hold_ms=args.pitch_hold_ms):
            midi = round(69 + 12 * math.log2(note.pitch_hz / 440))
            if 0 <= midi <= 127 and note.end - note.start >= args.min_length:
                spans.append(PitchSpan(float(note.start), float(note.end), midi))
        notes, warnings = notes_from_analysis(spans, words, args.min_length, word_notes=args.word_notes)
        report['warnings'].extend(warnings)
        if any(not 36 <= note.pitch <= 84 for note in notes):
            report['warnings'].append('Pitches outside the currently supported Lips writer range (36..84): review before export.')
        if not args.separate:
            report['warnings'].append('Unseparated audio: instruments may be detected as vocal notes.')
        report.update(pitch_spans=len(spans), pitches=[asdict(p) for p in spans], words=[asdict(w) for w in words],
                      note_layout='one note per word' if args.word_notes else 'pitch contour',
                      note_count=len(notes), pitch_device='cpu',
                      elapsed_seconds=round(time.monotonic() - started, 3))
        project = StudioProject(title=args.title or input_path.stem, artist=args.artist,
                                notes=notes, audio_path=str(input_path),
                                source='AI draft: SwiftF0 / ' + report.get('word_source', 'pitch only'),
                                warnings=report['warnings'])
        if args.lrc:
            from studio.lrc import attach_lrc
            attach_lrc(project, document, str(args.lrc.resolve()))
        elif words:
            project.draft_lyrics = project.lyric_text()
        if args.reference_text and words:
            report['transcript_comparison'] = word_error_rate(
                args.reference_text.read_text(encoding='utf-8-sig'), ' '.join(w.text for w in words))
        project.validate()
        save_project(project, args.out)
        with report_path.open('x', encoding='utf-8') as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        progress('complete', project=str(args.out.resolve()), report=str(report_path.resolve()),
                 notes=len(notes), elapsed_seconds=report['elapsed_seconds'])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path.home() / '.cache/openlips/ai')
    parser.add_argument('--ffmpeg')
    parser.add_argument('--progress-file', type=Path)
    parser.add_argument('--work-dir', type=Path, help='Parent for owned temporary decoding data')
    parser.add_argument('--separate', action='store_true')
    lyrics = parser.add_mutually_exclusive_group()
    lyrics.add_argument('--transcribe', action='store_true')
    lyrics.add_argument('--lrc', type=Path)
    parser.add_argument('--align-lrc', action='store_true', help='Estimate word times inside supplied LRC windows (English/German)')
    parser.add_argument('--reference-text', type=Path)
    parser.add_argument('--word-notes', action='store_true', help='Reviewable one-note-per-word draft; simplify melismas')
    parser.add_argument('--model', choices=('tiny', 'base', 'small', 'medium', 'large-v3'), default='base')
    parser.add_argument('--language', default='')
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda', 'amd', 'mps'), default='auto')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--duration', type=float, default=0)
    parser.add_argument('--fmin', type=float, default=65)
    parser.add_argument('--fmax', type=float, default=1100)
    parser.add_argument('--pitch-hold-ms', type=float, default=80)
    parser.add_argument('--min-length', type=float, default=.04)
    parser.add_argument('--title', default='')
    parser.add_argument('--artist', default='')
    args = parser.parse_args(argv)
    if args.align_lrc and not args.lrc:
        parser.error('--align-lrc requires --lrc')
    if not 1 <= args.threads <= 64 or not 0 <= args.duration <= 1800:
        parser.error('Invalid threads or duration')
    if not 0 < args.fmin < args.fmax or not 0 < args.min_length <= 2 or not 0 < args.pitch_hold_ms <= 1000:
        parser.error('Invalid pitch/segmentation settings')
    previous = sys.stdout
    if args.progress_file:
        protected = [args.input, args.out, args.out.with_suffix('.analysis.json'), args.lrc, args.reference_text]
        if any(path and path.resolve() == args.progress_file.resolve() for path in protected):
            parser.error('Progress log must not replace any input or project file')
        if args.progress_file.exists():
            parser.error('Progress log already exists; choose a new path')
        args.progress_file.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout = args.progress_file.open('x', encoding='utf-8', buffering=1)
    try:
        analyze(args)
    except Exception as exc:
        progress('error', message=str(exc), type=type(exc).__name__)
        return 1
    finally:
        if args.progress_file:
            sys.stdout.close()
            sys.stdout = previous
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
