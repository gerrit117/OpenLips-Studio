"""Build a new OG pair from a reviewed AI project, without copying a template heap."""
import argparse
import json
from pathlib import Path

from studio.ai_chart import PitchSpan, WordSpan, notes_from_analysis
from studio.model import load_project, save_project
from studio.exporters import export_owned_pair


def prepare(project_path, out, name, duration):
    project = load_project(project_path)
    report = json.loads(project_path.with_suffix('.analysis.json').read_text(encoding='utf-8'))
    if report.get('format') != 'openlips-ai-analysis' or not report.get('words'):
        raise ValueError('A matching word analysis report is required')
    pitches = [PitchSpan(**p) for p in report['pitches']] if report.get('pitches') else [
        PitchSpan(n.time, n.time + n.length, n.pitch) for n in project.ordered()]
    project.notes, warnings = notes_from_analysis(pitches, [WordSpan(**w) for w in report['words']], word_notes=True)
    project.warnings += warnings
    if duration <= project.duration:
        raise ValueError('Full media duration must exceed the last note')
    export_owned_pair(project, out, name, name + '.wma', name + '.wmv', duration=duration)
    save_project(project, out / 'reviewed-draft.olp')
    return dict(output=str(out.resolve()), note_count=len(project.notes), duration=duration,
                layout='one note per recognized word, dominant measured pitch',
                template_used=False, audio_modified=False, video_modified=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('project', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--name', default='Amazing')
    p.add_argument('--duration', type=float, required=True)
    args = p.parse_args()
    print(json.dumps(prepare(args.project, args.out, args.name, args.duration), indent=2))
