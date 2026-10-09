"""Test the build wrapper using synthetic tools/output, never Microsoft binaries."""
from pathlib import Path
import os
import struct
import subprocess

import pytest

from tools.build_xbox_client_probe import build

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Official SDK build wrapper is Windows-only')


def fixture(tmp_path):
    sdk = tmp_path/'sdk'
    (sdk/'bin/win32').mkdir(parents=True)
    for name in ('cl.exe', 'link.exe', 'imagexex.exe'):
        (sdk/'bin/win32'/name).touch()
    font = tmp_path/'test.ttf'
    font.write_bytes(b'synthetic-font')
    return sdk, font


def test_probe_refuses_to_overwrite(tmp_path):
    sdk, font = fixture(tmp_path)
    output = tmp_path/'existing'
    output.mkdir()
    with pytest.raises(FileExistsError):
        build(sdk, output, font)


def test_probe_tool_failures_propagate(tmp_path, monkeypatch):
    sdk, font = fixture(tmp_path)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(a[0], 2, b'synthetic error'))
    with pytest.raises(subprocess.CalledProcessError):
        build(sdk, tmp_path/'output', font)
    assert not (tmp_path/'output/verification.json').exists()


def test_probe_verifies_identity_and_keeps_hardware_unverified(tmp_path, monkeypatch):
    sdk, font = fixture(tmp_path)
    output = tmp_path/'output'
    def run(command, **kwargs):
        if Path(command[0]).name == 'imagexex.exe':
            header = b'XEX2' + struct.pack('>5I', 1, 0, 0, 0, 1)
            optional = struct.pack('>2I', 0x40006, 32)
            execution = struct.pack('>4I8x', 0, 0, 0, 0x4F4C5052)
            (output/'default.xex').write_bytes(header + optional + execution)
        return subprocess.CompletedProcess(command, 0, b'')
    monkeypatch.setattr(subprocess, 'run', run)
    build(sdk, output, font)
    import json
    record = json.loads((output/'verification.json').read_text())
    assert record['title_id'] == '4F4C5052' and record['hardware_verified'] is False
    assert (output/'media/client.ttf').read_bytes() == font.read_bytes()
