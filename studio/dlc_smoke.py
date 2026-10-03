"""Exercise the frozen DLC export with original synthetic video, not game assets."""
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree as ET
from studio.dlc_dialog import PackageWorker
from studio.dlc_media import bundled_tool
from studio.media import ffmpeg_encoder
from studio.model import StudioProject, EditorNote
from tools.build_dlc import verify_stfs
from tools.inventory_media_codecs import inspect_riff


def run(app, window, directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    try:
        source = directory / 'synthetic.mp4'
        result = subprocess.run([ffmpeg_encoder(), '-v', 'error', '-nostdin', '-n',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=17',
            '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=24:duration=17',
            '-map', '1:v', '-map', '0:a', '-c:v', 'libx264', '-c:a', 'aac', str(source)],
            capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise ValueError(result.stderr.decode('utf-8', errors='replace'))
        project = StudioProject(title='Synthetic export', artist='OpenLips',
            video_path=str(source), notes=[EditorNote(1, .5, 60, 'Test'), EditorNote(2, 1, 64, 'song')])
        output = directory
        worker = PackageWorker(project, output, window)
        window.dlc_smoke_worker = worker
        def failed(message):
            (directory / 'failure.txt').write_text(message, encoding='utf-8')
            app.exit(1)
        def completed(path):
            try:
                report = verify_stfs(path)
                extracted = directory / 'extracted'
                subprocess.run([bundled_tool('openlips_stfs'), 'extract', str(path), str(extracted)],
                               check=True, capture_output=True, timeout=120,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                for name, seconds in [('song.xWMA', 17), ('preview.xWMA', 15)]:
                    info = inspect_riff(extracted / name)
                    duration = info['dpds']['last_decoded_bytes'] / 192000
                    if abs(duration - seconds) >= .2:
                        raise ValueError('Unexpected prepared audio duration')
                    report[name] = info
                manifest = ET.parse(extracted / 'DLC.xml')
                preview_name = manifest.findtext('MusicVideos/MusicVideo/PreviewVideoUri')
                if preview_name != 'preview.wmv' or not (extracted / preview_name).is_file():
                    raise ValueError('Missing linked menu preview video')
                from tools.analyze_asf import inspect
                preview = inspect(extracted / preview_name)
                video = next(s for s in preview['streams'] if s.get('kind') == 'video')
                if (video['width'], video['height']) != (240, 136):
                    raise ValueError('Unexpected menu preview dimensions')
                report['preview_video'] = preview
                (directory / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                app.exit(0)
            except Exception as error:
                failed(str(error))
        worker.failed.connect(failed)
        worker.completed.connect(completed)
        worker.start()
    except Exception as error:
        (directory / 'failure.txt').write_text(str(error), encoding='utf-8')
        app.exit(1)
