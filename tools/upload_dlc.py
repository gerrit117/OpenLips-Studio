#!/usr/bin/env python3
"""Validate an existing OpenLips DLC and optionally upload it to Xbox FTP."""
import argparse
import ftplib
import getpass
import os
from pathlib import Path

try:
    from tools.build_dlc import verify_stfs, xbox_path, upload_package
except ModuleNotFoundError:
    from build_dlc import verify_stfs, xbox_path, upload_package


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('package', type=Path)
    p.add_argument('--host')
    p.add_argument('--port', type=int, default=21)
    p.add_argument('--user', default='xbox')
    p.add_argument('--root', default='Hdd1/Content')
    p.add_argument('--tls', action='store_true')
    p.add_argument('--upload', action='store_true', help='otherwise validate and show destination only')
    args = p.parse_args(argv)
    if args.upload and not args.host:
        p.error('--upload requires --host')
    report = verify_stfs(args.package)
    remote = xbox_path(args.package, args.root)
    print(f'unsigned LIVE DLC; SHA-256={report["sha256"]}; destination={remote}')
    if not args.upload:
        print('Dry run: no connection or upload performed.')
        return 0
    password = os.environ.get('OPENLIPS_FTP_PASSWORD') or getpass.getpass('Xbox FTP password: ')
    if not args.tls:
        print('WARNING: plain FTP is unencrypted. Use a trusted LAN.')
    with (ftplib.FTP_TLS if args.tls else ftplib.FTP)(timeout=30) as ftp:
        ftp.connect(args.host, args.port)
        ftp.login(args.user, password)
        if args.tls:
            ftp.prot_p()
        upload_package(ftp, args.package, remote)
    print('Upload verified by read-back SHA-256; new package published.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ftplib.Error) as error:
        raise SystemExit(f'DLC upload failed: {error}')
