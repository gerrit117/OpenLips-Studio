"""Publish validated local downloads using Git's existing GitHub credential helper."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
from urllib.parse import urlparse
import requests

REPO = 'gerrit117/OpenLips-Studio'


class GitHub:
    def __init__(self):
        result = subprocess.run(['git', 'credential', 'fill'],
            input='protocol=https\nhost=github.com\n\n', text=True, capture_output=True,
            env=dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never'), timeout=60)
        credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        if result.returncode or not credentials.get('password'):
            raise ValueError('No existing GitHub Git credential is available')
        self.session = requests.Session()
        self.session.headers.update(Authorization='Bearer ' + credentials['password'],
            Accept='application/vnd.github+json', **{'User-Agent':'OpenLips-release', 'X-GitHub-Api-Version':'2022-11-28'})

    def call(self, method, route, **kwargs):
        response = self.session.request(method, 'https://api.github.com/repos/' + REPO + '/' + route,
                                        timeout=120, **kwargs)
        if response.status_code == 404:
            return None
        if not response.ok:
            raise ValueError(f'GitHub {method} {route}: HTTP {response.status_code}')
        return response.json() if response.content else None

    def release(self, tag, assets, *, draft=False):
        for asset in map(Path, assets):
            if not re.fullmatch(r'OpenLips-Studio-[0-9]+\.[0-9]+\.[0-9]+(?:-beta\.[0-9]+)?-(?:windows-x64-setup\.exe|macos-(?:arm64|x64)\.dmg|linux-x64\.tar\.gz)', asset.name):
                raise ValueError('Main releases only accept system installation downloads: ' + asset.name)
        sha = subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
        if self.call('GET', 'commits/main')['sha'] != sha:
            raise ValueError('Push this commit to main before releasing')
        existing = self.call('GET', 'releases/tags/' + tag)
        if existing:
            ref = self.call('GET', 'git/ref/tags/' + tag)
            if ref and ref['object']['sha'] != sha:
                raise ValueError('Release tag belongs to another commit; bump the version')
            if not ref and existing['draft'] and existing['target_commitish'] != sha:
                existing = self.call('PATCH', f"releases/{existing['id']}", json={'target_commitish':sha})
            elif not ref and existing['target_commitish'] != sha:
                raise ValueError('Release targets another commit')
        notes = Path('CHANGELOG.md').read_text(encoding='utf-8').split('\n## ', 2)[1]
        body = notes.split('\n', 1)[1].strip() + '\n\n'
        body += ('Windows setup, macOS Apple Silicon/Intel DMGs and Linux installation archive. '
                 'Large AI runtimes are optional downloads. Final media encoding currently requires Windows; macOS/Linux need compatible game media. '
                 'The Community website is not yet publicly available. No original game or song media are distributed.')
        if not existing:
            existing = self.call('POST','releases',json=dict(tag_name=tag,target_commitish=sha,
                name='OpenLips Studio ' + tag[1:].replace('-beta.',' Beta '), body=body,draft=True,prerelease=False))
        uploaded = {item['name'] for item in self.call('GET', f"releases/{existing['id']}/assets?per_page=100")}
        for path in map(Path, assets):
            if path.name in uploaded:
                print('Preserved existing release asset:', path.name)
                continue
            if not path.is_file() or path.stat().st_size > 2*1024**3:
                raise ValueError('Missing or oversized release asset: ' + path.name)
            if path.suffix != '.sha256':
                checksum = Path(str(path)+'.sha256')
                with path.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if checksum.read_text(encoding='ascii').split()[0] != digest:
                    raise ValueError('Release checksum mismatch: ' + path.name)
            url = existing['upload_url'].split('{', 1)[0]
            if urlparse(url).hostname != 'uploads.github.com':
                raise ValueError('Unexpected release upload host')
            print('Uploading:', path.name, flush=True)
            with path.open('rb') as stream:
                response = self.session.post(url,params={'name':path.name},data=stream,timeout=900,
                    headers={'Content-Type':'application/octet-stream','Content-Length':str(path.stat().st_size)})
            if not response.ok:
                raise ValueError(f'Release upload failed: HTTP {response.status_code}')
        if not draft:
            self.call('PATCH', f"releases/{existing['id']}", json=dict(draft=False,prerelease=False,make_latest='true'))
        print(existing['html_url'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag')
    parser.add_argument('--asset',type=Path,action='append',default=[])
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--draft',action='store_true')
    parser.add_argument('--run', type=int)
    parser.add_argument('--job-log', type=int)
    args = parser.parse_args()
    client = GitHub()
    if args.job_log:
        response = client.session.get('https://api.github.com/repos/' + REPO + f'/actions/jobs/{args.job_log}/logs',timeout=120)
        response.raise_for_status()
        print(response.text[-20000:])
    elif args.run:
        data = client.call('GET',f'actions/runs/{args.run}/jobs?per_page=100')
        print(json.dumps([dict(id=j['id'],name=j['name'],status=j['status'],conclusion=j['conclusion'],
            steps=[dict(name=s['name'],status=s['status'],conclusion=s['conclusion']) for s in j['steps']]) for j in data['jobs']]))
    elif args.status:
        data = client.call('GET','actions/workflows/studio.yml/runs?per_page=3')
        print(json.dumps([dict(id=r['id'],status=r['status'],conclusion=r['conclusion'],sha=r['head_sha']) for r in data['workflow_runs']]))
    elif args.tag:
        client.release(args.tag, args.asset, draft=args.draft)
    else:
        parser.error('Choose --status, --run, --job-log or --tag')


if __name__ == '__main__':
    main()
