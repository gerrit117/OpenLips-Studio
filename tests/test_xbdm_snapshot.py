"""Bounded read-only protocol handling, no console credentials or game data."""
import io
import pytest
from tools.xbdm_snapshot import response


def test_single_line_and_multiline():
    assert response(io.BytesIO(b'201- connected\r\n'))['status'] == '201- connected'
    assert response(io.BytesIO(b'202- list\r\n42\r\n.\r\n'))['lines'] == ['42']


def test_bad_and_unterminated_responses():
    for value in (b'not XBDM\r\n', b'201- unfinished', b'202- list\r\nmissing terminator\r\n', b'201- ' + b'x' * 4096 + b'\n'):
        with pytest.raises(ValueError):
            response(io.BytesIO(value))
