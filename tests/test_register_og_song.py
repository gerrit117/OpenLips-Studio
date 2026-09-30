import sqlite3
from contextlib import closing

import pytest

from tools.register_og_song import COLUMNS, register


def catalog(path):
    with closing(sqlite3.connect(path)) as c:
        c.execute('CREATE TABLE Music ('+','.join(COLUMNS)+')')
        c.execute('CREATE TABLE PlayOption (ID, MasterOffset)')
        c.execute('INSERT INTO PlayOption VALUES (?,?)', ('original', 0.25))
        row = dict.fromkeys(COLUMNS, 0)
        row.update(UintID='0x00010001', ID='original', TitleID='0x4D530888',
                   DiscIndex=3, Source=0, AudioState=2, ChartState=2)
        c.execute('INSERT INTO Music VALUES ('+','.join('?' for _ in COLUMNS)+')',
                  tuple(row.values()))
        c.commit()


def add(source, output, **kwargs):
    return register(source, output, title='Synthetic Song', artist='Test Artist',
                    asset_stem=kwargs.pop('asset_stem', r'Levels\Custom\Test\Test'),
                    uint_id=kwargs.pop('uint_id', 0x19001),
                    song_id=kwargs.pop('song_id', 'custom-1'), **kwargs)


def test_copy_preserves_source_and_other_tables(tmp_path):
    source, output = tmp_path/'source', tmp_path/'out'
    catalog(source)
    before = source.read_bytes()
    result = add(source, output)
    assert result['final_count'] == 2
    assert source.read_bytes() == before
    with sqlite3.connect(output) as c:
        assert c.execute('SELECT * FROM PlayOption').fetchall() == [('original', .25)]
        c.row_factory = sqlite3.Row
        row = dict(c.execute('SELECT * FROM Music WHERE ID=?', ('custom-1',)).fetchone())
        assert row['Title'] == 'Synthetic Song'
        assert row['ChartUri'] == r'Levels\Custom\Test\Test.ixb'
        assert row['LyricUri'].endswith('_Lyric.ixb')
        assert row['LeaderBoardID'] == 0


@pytest.mark.parametrize('kwargs', [{'song_id':'original'}, {'uint_id':0x10001},
                                   {'asset_stem':r'..\escape'}, {'asset_stem':r'C:\escape'},
                                   {'asset_stem':r'\escape'},
                                   {'asset_stem':''}, {'uint_id':-1}])
def test_refuses_invalid_registration(tmp_path, kwargs):
    source, output = tmp_path/'source', tmp_path/'out'
    catalog(source)
    with pytest.raises(ValueError):
        add(source, output, **kwargs)
    assert not output.exists()


def test_no_overwrite(tmp_path):
    source, output = tmp_path/'source', tmp_path/'out'
    catalog(source)
    output.write_bytes(b'keep')
    with pytest.raises(ValueError):
        add(source, output)
    assert output.read_bytes() == b'keep'
    with pytest.raises(ValueError):
        add(source, source)


def test_unknown_schema_refused(tmp_path):
    source, output = tmp_path/'source', tmp_path/'out'
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE Music (ID)')
    with pytest.raises(ValueError, match='schema'):
        add(source, output)


def test_foreign_family_refused(tmp_path):
    source, output = tmp_path/'source', tmp_path/'out'
    catalog(source)
    with closing(sqlite3.connect(source)) as c:
        c.execute('UPDATE Music SET DiscIndex=10')
        c.commit()
    with pytest.raises(ValueError, match='family'):
        add(source, output)
    assert not output.exists()


def test_publish_failure_leaves_source_and_cleans_temporary(tmp_path, monkeypatch):
    source, output = tmp_path/'source', tmp_path/'out'
    catalog(source)
    before = source.read_bytes()
    def fail(*args):
        raise OSError('publication unavailable')
    monkeypatch.setattr('tools.register_og_song.os.link', fail)
    with pytest.raises(OSError, match='publication'):
        add(source, output)
    assert source.read_bytes() == before
    assert not output.exists()
    assert list(tmp_path.glob('out.*.tmp')) == []
