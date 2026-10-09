from pathlib import Path
import yaml


def test_all_native_targets_build_usdb_before_studio():
    root = Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load((root / '.github/workflows/studio.yml').read_text())
    desktop = workflow['jobs']['desktop']
    assert set(desktop['strategy']['matrix']['os']) == {'windows-2022','macos-14','macos-15-intel','ubuntu-22.04'}
    steps = [step.get('run', '') for step in desktop['steps']]
    build = steps.index('python -m tools.build_usdb_runtime')
    freeze = steps.index('python -m PyInstaller --noconfirm OpenLipsStudio.spec')
    assert build < freeze
    step = desktop['steps'][build]
    assert 'if' not in step
    assert workflow['jobs']['release']['permissions']['contents'] == 'write'
