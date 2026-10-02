import copy
import pytest

from tools.run_xenia_test import switch


def config(tmp_path, monkeypatch):
    monkeypatch.setattr('tools.run_xenia_test.ensure_closed', lambda executable: None)
    root = tmp_path / 'game'
    root.mkdir()
    exe = tmp_path / 'xenia.exe'
    exe.write_bytes(b'synthetic executable placeholder')
    files = []
    for index in range(2):
        target = root / f'chart{index}.X360'
        target.write_bytes(b'pretest')
        source = tmp_path / f'new{index}'
        source.write_bytes(b'AI')
        baseline = tmp_path / f'baseline{index}'
        baseline.write_bytes(b'original')
        files.append(dict(relative=target.name, source=str(source), baseline=str(baseline)))
    return dict(game_root=str(root), xenia=str(exe), state=str(tmp_path / 'backup/state.json'), files=files)


def test_baseline_ai_restore_and_repeat(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    target = tmp_path / 'game/chart0.X360'
    switch(cfg, 'baseline')
    assert target.read_bytes() == b'original'
    switch(cfg)
    assert target.read_bytes() == b'AI'
    switch(cfg, 'restore')
    assert target.read_bytes() == b'pretest'
    switch(cfg)
    assert target.read_bytes() == b'AI'


def test_manual_changes_never_overwritten(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    switch(cfg)
    target = tmp_path / 'game/chart0.X360'
    target.write_bytes(b'user edit')
    with pytest.raises(ValueError, match='outside this test'):
        switch(cfg, 'restore')
    assert target.read_bytes() == b'user edit'


def test_restore_without_generated_files(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    switch(cfg)
    for item in cfg['files']:
        from pathlib import Path
        Path(item['source']).unlink()
    switch(cfg, 'restore')
    assert (tmp_path / 'game/chart0.X360').read_bytes() == b'pretest'


def test_escape_rejected(tmp_path, monkeypatch):
    cfg = config(tmp_path, monkeypatch)
    cfg['files'][0]['relative'] = '../xenia.exe'
    with pytest.raises(ValueError):
        switch(cfg)
