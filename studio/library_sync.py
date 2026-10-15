"""Resumable LAN synchronization with explicit, opt-in local deletion propagation."""
from pathlib import Path
import re
import tempfile
import os
import hashlib

from studio.library_bundle import write_bundle
from studio.model import StudioProject, load_project


def copy_packages(library, identifiers, directory, progress=lambda message: None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for identifier in identifiers:
        source = library.package_path(identifier)
        from tools.build_dlc import verify_stfs
        if verify_stfs(source)['sha256'] != identifier:
            raise ValueError('Managed DLC checksum changed')
        target = directory / source.name
        temporary = None
        try:
            digest = hashlib.sha256()
            with source.open('rb') as src, tempfile.NamedTemporaryFile(dir=directory, delete=False) as dst:
                temporary = Path(dst.name)
                for chunk in iter(lambda: src.read(1024 * 1024), b''):
                    dst.write(chunk)
                    digest.update(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            if digest.hexdigest() != identifier:
                raise ValueError('DLC changed while copying')
            try:
                os.link(temporary, target)
            except FileExistsError:
                from tools.build_dlc import sha256
                if target.is_symlink() or sha256(target) != identifier:
                    raise FileExistsError('Existing destination differs; not overwritten')
            outputs.append(target)
            progress(source.name)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
    return outputs


def upload_project(client, project, progress=lambda message: None, *, remote_id=None):
    with tempfile.TemporaryDirectory(prefix='openlips-sync-') as folder:
        bundle = Path(folder) / 'song.zip'
        write_bundle(project, bundle, progress)
        endpoint = '/api/v1/project-bundles' if remote_id is None else f'/api/v1/projects/{remote_id}/bundle'
        return client.upload_file(endpoint, bundle, progress=progress)['id']


def download_project(client, library, identifier, progress=lambda message: None, *, local_id=None):
    if not re.fullmatch(r'[a-f0-9]{32}', identifier):
        raise ValueError('Invalid remote project ID')
    data = client.request('GET', '/api/v1/projects/' + identifier)
    payload = data['project']
    for field in ('audio', 'video', 'cover'):
        payload[field + '_path'] = ''
    project = StudioProject.from_payload(payload)
    with tempfile.TemporaryDirectory(dir=library.root / '.staging') as folder:
        for field, media in data['media'].items():
            if field not in ('audio', 'video', 'cover') or not re.fullmatch(
                    r'[a-f0-9]{64}\.[a-z0-9]{1,16}', media['filename']):
                raise ValueError('Invalid remote media metadata')
            path = Path(folder) / media['filename']
            progress(media['filename'])
            client.request('GET', f'/api/v1/projects/{identifier}/media/{field}', target=path,
                expected_hash=media['sha256'], expected_bytes=media['bytes'])
            setattr(project, field + '_path', str(path))
        return library.add_project(project, progress, identifier=local_id)


def sync_library(library, client, progress=lambda message: None, *, propagate_deletions=False):
    identity = client.request('GET', '/api/v1/identity')
    server_id = identity['server_id']
    if not isinstance(server_id, str) or not re.fullmatch(r'[a-f0-9]{32}', server_id):
        raise ValueError('Invalid library identity')
    remote = client.request('GET', '/api/v1/library')
    result = dict(uploaded=0, downloaded=0, skipped=0, deleted=0, errors=[])

    def remember_project(peer, record):
        known = next((r for r in remote.get('projects',[]) if r['id'] == peer),None)
        if known is None:
            known = dict(record,id=peer)
            remote.setdefault('projects',[]).append(known)
        return known.get('modified','')

    # Editing files keep their library identity across ordinary saves.
    for path in sorted((library.root / 'workspace').glob('*.olp')):
        try:
            progress(path.name)
            library.save_source(load_project(path), path, progress, only_if_newer=True)
        except Exception as error:
            result['errors'].append(f'{path.name}: {error}')
    for kind, records in (('projects', library.projects()), ('packages', library.packages())):
        remote_ids = {r['id'] for r in remote.get(kind, [])}
        links = library.sync_links(server_id, kind)
        local_ids = {r['id'] for r in records}
        tombstones = library.deleted(kind)
        live_peers = {peer for local,peer in links if local in local_ids}
        suppressed = {peer for local,peer in links if local in tombstones and local not in local_ids and peer not in live_peers}
        if propagate_deletions:
            for peer in sorted(suppressed & remote_ids):
                try:
                    client.request('DELETE', f'/api/v1/{kind}/{peer}')
                    result['deleted'] += 1
                    remote_ids.discard(peer)
                except Exception as error:
                    result['errors'].append(f'{peer}: {error}')
        for record in records:
            identifier = record['id']
            linked = next((peer for local,peer in links if local == identifier and peer in remote_ids),None)
            try:
                if linked and kind == 'projects':
                    revision = library.revision(identifier)
                    baseline = library.synced_revision(server_id, identifier)
                    peer_record = next(r for r in remote[kind] if r['id'] == linked)
                    peer_date, local_date = peer_record.get('modified',''), record.get('modified','')
                    remote_baseline = library.synced_remote_date(server_id,identifier)
                    local_changed = baseline is not None and revision != baseline
                    remote_changed = peer_date != remote_baseline if remote_baseline is not None else peer_date != local_date
                    if local_changed and remote_changed:
                        raise ValueError('Project changed on both peers; resolve before syncing')
                    if local_changed or (baseline is None and local_date > peer_date):
                        shared = any(local != identifier and local in local_ids and peer == linked for local,peer in links)
                        target = upload_project(client,load_project(library.project_path(identifier)),progress,
                                                remote_id=None if shared else linked)
                        if target != linked:
                            library.replace_remote_link(server_id,kind,identifier,target)
                            links = [(local,peer) for local,peer in links if local != identifier]+[(identifier,target)]
                            remote_ids.add(target)
                            peer_date = remember_project(target,record)
                        else:
                            peer_record.update(record,id=linked)
                            peer_date = local_date
                        result['uploaded'] += 1
                    elif peer_date and remote_changed:
                        download_project(client,library,linked,progress,local_id=identifier)
                        result['downloaded'] += 1
                    else:
                        result['skipped'] += 1
                    library.synced_revision(server_id,identifier,library.revision(identifier),remote_modified=peer_date)
                    continue
                if linked:
                    result['skipped'] += 1
                    continue
                progress(record['title'])
                if kind == 'projects':
                    peer = upload_project(client, load_project(library.project_path(identifier)), progress)
                elif identifier in remote_ids:
                    peer = identifier
                else:
                    peer = client.upload_file('/api/v1/packages', library.package_path(identifier), progress=progress)['id']
                    if peer != identifier:
                        raise ValueError('Uploaded DLC checksum does not match')
                library.link_remote(server_id, kind, identifier, peer)
                links.append((identifier, peer))
                if kind == 'projects':
                    remote_ids.add(peer)
                    peer_date = remember_project(peer,record)
                    library.synced_revision(server_id,identifier,library.revision(identifier),remote_modified=peer_date)
                result['uploaded'] += 1
            except Exception as error:
                result['errors'].append(f'{record["title"]}: {error}')
        for record in remote.get(kind, []):
            peer = record['id']
            if peer in suppressed:
                continue
            if any(remote_id == peer and local in local_ids for local, remote_id in links):
                continue
            try:
                progress(record['title'])
                if kind == 'projects':
                    identifier = download_project(client, library, peer, progress)
                else:
                    if not re.fullmatch(r'[a-f0-9]{64}', peer) or not re.fullmatch(r'[A-Fa-f0-9]{42}', record['filename']):
                        raise ValueError('Invalid remote DLC metadata')
                    path = library.root / 'publish' / record['filename']
                    client.request('GET', '/api/v1/packages/' + peer, target=path,
                        expected_hash=peer, expected_bytes=record['bytes'])
                    identifier = library.add_package(path, progress=progress)
                library.link_remote(server_id, kind, identifier, peer)
                local_ids.add(identifier)
                links.append((identifier, peer))
                if kind == 'projects':
                    library.synced_revision(server_id,identifier,library.revision(identifier),remote_modified=record.get('modified',''))
                result['downloaded'] += 1
            except Exception as error:
                result['errors'].append(f'{record["title"]}: {error}')
    return result
