"""A YouTube reference is separate from a local VIDEO filename."""
from urllib.parse import parse_qs
from tools.song_bundle import youtube_reference


def reference_video(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if value.startswith('v='):
        value = parse_qs(value, separator=',').get('v', [''])[0]
    try:
        return youtube_reference(value) or ''
    except ValueError:
        return ''


def metadata_reference(metadata):
    return reference_video(metadata.get('VIDEOURL', '')) or reference_video(metadata.get('VIDEO', ''))
