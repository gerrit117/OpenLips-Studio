"""Prepare synthetic, isolated hardware test DLCs. Never install or patch a game."""
import argparse
import json
from pathlib import Path

from studio.model import EditorNote, StudioProject, save_project
from tools.build_dlc import build_package, make_manifest, sha256
from tools.build_media_codec_tests import build as audio_probes, run
from tools.build_mpeg4_codec_tests import build as video_probes


def build(output):
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Choose a new codec-test directory')
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from studio.media import ffmpeg_encoder
    from studio.dlc_media import prepare_dlc_media, bundled_tool
    from studio.exporters import export_owned_pair
    output.mkdir(parents=True)
    source = output / 'synthetic.mp4'
    run([ffmpeg_encoder(), '-nostdin', '-v', 'error', '-n', '-f', 'lavfi', '-i',
        'testsrc2=size=768x432:rate=24000/1001:duration=70', '-f', 'lavfi', '-i',
        'sine=frequency=261.6256:sample_rate=48000:duration=70', '-c:v', 'libx264',
        '-preset', 'veryfast', '-crf', '24', '-c:a', 'aac', '-ac', '2', str(source)])
    project = StudioProject(title='Codec control', artist='OpenLips tests', video_path=str(source),
        notes=[EditorNote(t, 2, 60, f'Test {int(t)}', line_break_after=True)
               for t in (1, 10, 20, 30, 40, 50, 60)])
    project.notes[-1].line_break_after = False
    media, duration = prepare_dlc_media(project, output / 'media', lambda message: None)
    pair = export_owned_pair(project, output / 'pair', 'test', media['audio'].stem,
                             media['video'].stem, duration=duration)
    video_probes(media['video'], output / 'video-probes')
    audio_probes(media['video'], output / 'audio-probes')
    variants = [('01-original', media['video']),
                ('02-remux-control', output / 'video-probes/remux-control.wmv'),
                ('03-mpeg4-mp4s', output / 'video-probes/mpeg4-mp4s.wmv'),
                ('04-msmpeg4-mp43', output / 'video-probes/msmpeg4v3-mp43.wmv'),
                ('05-msmpeg4-mp42', output / 'video-probes/msmpeg4v2-mp42.wmv'),
                ('06-vc1-wma-standard', output / 'audio-probes/vc1-wma-standard.wmv')]
    records = []
    for index, (label, video) in enumerate(variants):
        folder = output / label
        folder.mkdir()
        files = {path.name: path for key, path in media.items() if key != 'video'}
        files[media['video'].name] = video
        files.update({path.name: path for path in pair.iterdir() if path.suffix == '.X360'})
        assets = {key: path.name for key, path in media.items()}
        assets.update(chart='test.X360', lyric='test_Lyric.X360')
        metadata = make_manifest('Codec ' + label, 'OpenLips tests', 0x73F10001 + index,
                                 duration, assets, preview_lyric='Synthetic codec test')
        report = build_package(bundled_tool('openlips_stfs'), files, metadata, folder,
                               'OpenLips codec ' + label, canonical_name=True)
        records.append(dict(variant=label, package=report['output_path'], sha256=report['sha256'],
                            video_sha256=sha256(video), xbox_result='not_tested'))
    save_project(project, output / 'synthetic.olp')
    report = dict(duration=duration, synthetic_only=True, game_files_modified=False,
        common_assets={key: sha256(path) for key, path in files.items() if key != media['video'].name},
        tests=records, instructions='Test original and remux first, play each to its 70-second end. All preview clips use the same original codec. Do not infer full-song playback from a working menu preview.')
    (output / 'tests.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = build(args.out)
    print(f"Prepared {len(report['tests'])} synthetic test DLCs; hardware playback remains untested")


if __name__ == '__main__':
    main()
