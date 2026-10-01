import pytest

from tools import prepare_catalog_refresh_test as tool


def test_unknown_build_writes_nothing(tmp_path):
    source = tmp_path / 'source.lua'
    source.write_bytes(b'synthetic unknown build')
    output = tmp_path / 'bundle'
    with pytest.raises(ValueError, match='Unsupported'):
        tool.prepare(source, output)
    assert not output.exists()


def test_prepare_preserves_source_and_original_prefix(tmp_path, monkeypatch):
    source = tmp_path / 'source.lua'
    data = b'-- synthetic\r\n'
    source.write_bytes(data)
    monkeypatch.setattr(tool, 'SUPPORTED_SHA256', tool.digest(data))
    output = tmp_path / 'bundle'
    manifest = tool.prepare(source, output)
    assert source.read_bytes() == data
    for name in ('observe.lua', 'coalesce.lua'):
        assert (output / name).read_bytes().startswith(data)
    assert manifest['status'].startswith('prepared_not_installed')
    with pytest.raises(FileExistsError):
        tool.prepare(source, output)


def test_invalid_window_does_not_create_output(tmp_path, monkeypatch):
    source = tmp_path / 'source.lua'
    source.write_bytes(b'synthetic')
    monkeypatch.setattr(tool, 'SUPPORTED_SHA256', tool.digest(b'synthetic'))
    with pytest.raises(ValueError):
        tool.prepare(source, tmp_path / 'bundle', 0)
    assert not (tmp_path / 'bundle').exists()


def test_rollback_refuses_foreign_changes(tmp_path, monkeypatch):
    source = tmp_path / 'source.lua'
    source.write_bytes(b'synthetic')
    monkeypatch.setattr(tool, 'SUPPORTED_SHA256', tool.digest(b'synthetic'))
    bundle = tmp_path / 'bundle'
    tool.prepare(source, bundle)
    source.write_bytes(b'new user work')
    with pytest.raises(ValueError, match='independently'):
        tool.restore(bundle, source)
    assert source.read_bytes() == b'new user work'


def test_rollback_restores_and_preserves_candidate(tmp_path, monkeypatch):
    source = tmp_path / 'source.lua'
    source.write_bytes(b'synthetic')
    monkeypatch.setattr(tool, 'SUPPORTED_SHA256', tool.digest(b'synthetic'))
    bundle = tmp_path / 'bundle'
    tool.prepare(source, bundle)
    candidate = (bundle / 'coalesce.lua').read_bytes()
    source.write_bytes(candidate)
    tool.restore(bundle, source)
    assert source.read_bytes() == b'synthetic'
    assert source.with_name('source.lua.before-rollback').read_bytes() == candidate


def test_modes_preserve_callbacks_and_do_not_use_xmp_as_flush_gate():
    observe = tool.hook('observe').decode()
    optimized = tool.hook('coalesce').decode()
    assert 'local optimize = false' in observe
    assert 'local optimize = true' in optimized
    assert 'frame + 30' in optimized
    assert 'if not pending then due =' in optimized
    assert 'return evaluate(self, ...)' in optimized
    assert 'return selected(self, ...)' in optimized
    assert 'OnSongEnumerationFinished' not in optimized


@pytest.mark.parametrize('mode, expected', [('observe', 600), ('coalesce', 1)])
def test_lua_51_burst_and_original_eval(mode, expected):
    lua_module = pytest.importorskip('lupa.lua51')
    lua = lua_module.LuaRuntime()
    lua.execute('''
        print = function(...) end
        calls, evaluations, leaves = 0, 0, 0
        PlayMenu2Properties = {bChallengeEnumeration = false}
        PlayMenu2 = {bActivePlayMenu = true, Play = {}}
        PlayMenu2.Play.OnMusicIndexInstalled = function(self, sender)
            calls = calls + 1
        end
        PlayMenu2.Play.EvalState = function(self) evaluations = evaluations + 1 end
        PlayMenu2.Play.OnSelectCompleted = function(self) end
        PlayMenu2.OnLeaveState = function(self) leaves = leaves + 1 end
    ''')
    lua.execute(tool.hook(mode).decode())
    lua.execute('''
        for i = 1, 600 do PlayMenu2.Play:OnMusicIndexInstalled(i) end
        for i = 1, 30 do PlayMenu2.Play:EvalState() end
    ''')
    assert lua.globals().calls == expected
    assert lua.globals().evaluations == 30
    lua.execute('PlayMenu2.Play:OnMusicIndexInstalled(601); PlayMenu2:OnLeaveState()')
    assert lua.globals().calls == expected + 1
    assert lua.globals().leaves == 1


def test_lua_51_continuous_events_do_not_starve_refresh():
    lua_module = pytest.importorskip('lupa.lua51')
    lua = lua_module.LuaRuntime()
    lua.execute('''
        print = function(...) end
        calls = 0
        PlayMenu2Properties = {bChallengeEnumeration = false}
        PlayMenu2 = {bActivePlayMenu = true, Play = {
            OnMusicIndexInstalled = function(self) calls = calls + 1 end,
            EvalState = function(self) end,
            OnSelectCompleted = function(self) end
        }, OnLeaveState = function(self) end}
    ''')
    lua.execute(tool.hook('coalesce').decode())
    lua.execute('''
        for i = 1, 90 do
            PlayMenu2.Play:OnMusicIndexInstalled(i)
            PlayMenu2.Play:EvalState()
        end
    ''')
    assert lua.globals().calls == 3
    lua.execute('''
        PlayMenu2Properties.bChallengeEnumeration = true
        PlayMenu2.Play:OnMusicIndexInstalled(91)
        PlayMenu2.bActivePlayMenu = false
        PlayMenu2.Play:OnMusicIndexInstalled(92)
    ''')
    assert lua.globals().calls == 5
