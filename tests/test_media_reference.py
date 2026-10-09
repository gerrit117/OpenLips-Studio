from studio.media_reference import reference_video, metadata_reference


def test_reference_prioritizes_videourl_over_local_filename():
    assert metadata_reference({'VIDEO': 'song.mp4', 'VIDEOURL': 'https://youtu.be/abcdefghijk'}) == \
        'https://www.youtube.com/watch?v=abcdefghijk'
    assert reference_video('v=abcdefghijk,co=cover.jpg').endswith('abcdefghijk')
    assert reference_video('song.mp4') == ''
    assert reference_video('https://example.com/watch?v=abcdefghijk') == ''
