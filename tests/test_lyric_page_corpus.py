from tools.analyze_lyric_pages import distribution, inspect_pair, summarize, corpus
from tools.build_owned_chart import build_owned_pair
from tools.write_template_chart import Note, SongChart


def test_distribution_empty_and_interpolated():
    assert distribution([]) == {'count': 0}
    result = distribution([1, 3, 5, 7])
    assert result['p50'] == 4
    assert result['min'] == 1
    assert result['max'] == 7


def test_owned_pages_and_duplicate_corpus(tmp_path):
    source = SongChart([Note(2, .4, 60, 'Hello', line_break_after=True),
                        Note(4, .5, 62, 'world')])
    chart, lyric = build_owned_pair(source, 'Synthetic', 'Audio/Synthetic')
    chart_path = tmp_path / 'Synthetic.X360'
    lyric_path = tmp_path / 'Synthetic_Lyric.X360'
    chart_path.write_bytes(chart)
    lyric_path.write_bytes(lyric)
    row = inspect_pair(chart_path, lyric_path)
    normal = next(t for t in row['tracks'] if t['name'] == 'Lyric')
    assert [p['characters'] for p in normal['pages']] == [5, 5]
    assert [p['notes'] for p in normal['pages']] == [1, 1]
    assert normal['anomalies'] == {}
    summary = summarize([dict(row, status='parsed')])
    assert summary['transition_count'] == 1
    assert summary['transition_occurrences']['word_end'] == 1
    result = corpus([('one', tmp_path), ('copy', tmp_path)], tmp_path)
    assert result['physical_chart_files'] == 2
    assert result['summary']['unique_pairs'] == 1
    assert result['summary']['nonempty_normal_pages'] == 2
    assert result['unpaired_lyric_files'] == []
