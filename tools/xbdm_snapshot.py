"""Read-only Xbox 360 XBDM diagnostics. Never pauses, writes or launches a title."""
import argparse
import json
from pathlib import Path
import re
import socket
import time

from studio.xbox_transfer import private_address
from tools.build_dlc import sha256


def response(stream):
    def line():
        value = stream.readline(4097)
        if not value.endswith(b'\n') or len(value) > 4096:
            raise ValueError('Incomplete or oversized XBDM response')
        return value.rstrip(b'\r\n').decode('ascii', errors='replace')
    status = line()
    if not re.match(r'^\d{3}[- ]', status):
        raise ValueError('Not an XBDM response')
    lines = []
    if status.startswith('202'):
        for _ in range(2048):
            value = line()
            if value == '.':
                break
            lines.append(value)
        else:
            raise ValueError('XBDM response exceeded safety limit')
    return dict(status=status, lines=lines)


def snapshot(host, port=730):
    if not 1 <= port <= 65535:
        raise ValueError('Invalid XBDM port')
    address = private_address(host)
    with socket.create_connection((address, port), timeout=5) as connection:
        connection.settimeout(5)
        with connection.makefile('rb') as stream:
            result = dict(host=address, captured_at=time.time(), greeting=response(stream))
            def query(command):
                connection.sendall(command.encode('ascii') + b'\r\n')
                return response(stream)
            for command in ('dmversion', 'modules', 'threads'):
                result[command] = query(command)
            ids = []
            for line in result['threads']['lines']:
                value = line.strip()
                if re.fullmatch(r'(?:0x[0-9a-fA-F]{1,8}|[0-9]{1,10})', value):
                    identifier = int(value, 16 if value.startswith('0x') else 10)
                    if 0 < identifier <= 0xFFFFFFFF:
                        ids.append(identifier)
            result['thread_info'] = {f'{identifier:08X}': query(f'threadinfo thread=0x{identifier:08X}')
                                     for identifier in ids[:128]}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=730)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--xex', type=Path, help='Optional local executable hash, read only')
    args = parser.parse_args(argv)
    result = snapshot(args.host, args.port)
    if args.xex:
        result['local_xex_sha256'] = sha256(args.xex)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(f'Saved read-only XBDM snapshot: {args.out}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
