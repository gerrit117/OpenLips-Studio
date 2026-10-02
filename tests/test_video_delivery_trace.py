from tools.analyze_video_delivery_trace import summarize


def test_delivery_separates_reused_objects_and_demux():
    text = '\n'.join([
        'site=824B1DC8 owner=10000000 demux=20000000 hit=1 time_hi=00000000 time_lo=00000021 written=00001000 eof=00000000',
        'site=824B1DC8 owner=10000000 demux=20000000 hit=120 time_hi=00000000 time_lo=00000042 written=00001000 eof=00000000',
        'site=824B1DC8 owner=10000000 demux=30000000 hit=240 time_hi=00000001 time_lo=00000000 written=00000000 eof=00000001',
    ])
    rows = summarize(text)
    assert len(rows) == 2
    assert rows[0]['timestamp_last_ms'] == 66
    assert rows[0]['timestamp_unique'] == 2
    assert rows[1]['timestamp_first_ms'] == 2**32


def test_delivery_regressions_are_reported_not_hidden():
    text = '\n'.join(f'site=824B1DC8 owner=10000000 demux=20000000 hit={i} time_hi=00000000 time_lo={time:08X} written=00001000 eof=00000000'
                     for i, time in enumerate([100, 200, 100], 1))
    assert summarize(text)[0]['timestamp_regressions'] == 1


def test_unreadable_timestamp_does_not_create_false_consecutive_delta():
    text = '\n'.join(
        f'site=824B1DC8 owner=10000000 demux=20000000 hit={i} time_hi={hi} time_lo={lo} written=00001000 eof=00000000'
        for i, hi, lo in [(1, '00000000', '00000000'),
                          (2, 'unreadable', 'unreadable'),
                          (3, '00000000', '00000064'),
                          (4, '00000000', '0000008E')])
    assert summarize(text)[0]['consecutive_timestamp_deltas_ms'] == {42: 1}
