"""Configuration boundaries; no Docker daemon or real media is needed."""
from pathlib import Path
import yaml


def test_docker_is_unprivileged_and_context_is_not_the_private_website():
    root=Path(__file__).resolve().parents[1]
    compose=yaml.safe_load((root/'library_server/compose.yaml').read_text())
    service=compose['services']['library']
    assert service['read_only']
    assert 'no-new-privileges:true' in service['security_opt']
    assert 'network_mode' not in service
    assert service['ports']==['${OPENLIPS_WEB_PORT:-8765}:8765']
    assert service['image']=='ghcr.io/gerrit117/openlips-library:latest'
    assert all('/var/run/docker.sock' not in value for value in service['volumes'])
    docker=(root/'library_server/Dockerfile').read_text()
    assert 'library_server.entrypoint' in docker
    assert 'COPY web/' not in docker and 'COPY private/' not in docker
    ignore=(root/'library_server/Dockerfile.dockerignore').read_text()
    assert ignore.startswith('**\n')
    assert '!web/' not in ignore and '!private/' not in ignore
    assert '!library_server/**' not in ignore
    assert '!library_server/static/index.html' in ignore


def test_web_ui_is_local_asset_only_and_does_not_save_access_keys():
    root=Path(__file__).resolve().parents[1]
    html=(root/'library_server/static/index.html').read_text(encoding='utf-8')
    js=(root/'library_server/static/app.js').read_text(encoding='utf-8')
    assert 'https://fonts' not in html
    assert '<script src="https://' not in html
    assert "localStorage.setItem('api_token'" not in js
    assert "credentials:'omit'" in js


def test_container_publish_tests_before_push_and_uses_temporary_token():
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.safe_load((root/'.github/workflows/library-container.yml').read_text())
    job=workflow['jobs']['build-test-publish']
    assert job['permissions']=={'contents':'read','packages':'write'}
    steps=job['steps']
    test=next(i for i,s in enumerate(steps) if s.get('run')=='python3 library_server/container_smoke.py')
    publish=next(i for i,s in enumerate(steps) if s.get('name')=='Publish tested image')
    assert test<publish
    assert any(s.get('with',{}).get('password')=='${{ secrets.GITHUB_TOKEN }}' for s in steps)
    assert 'latest' in steps[publish]['run'] and 'sha-$REVISION' in steps[publish]['run']


def test_unraid_template_uses_one_port_bridge_and_persistent_data():
    from xml.etree import ElementTree as ET
    root=Path(__file__).resolve().parents[1]
    template=ET.parse(root/'library_server/unraid/OpenLips-Library.xml').getroot()
    assert template.findtext('Repository')=='ghcr.io/gerrit117/openlips-library:latest'
    assert template.findtext('Network')=='bridge'
    assert template.findtext('Privileged')=='false'
    assert any(c.get('Target')=='/data' and c.get('Type')=='Path' for c in template.findall('Config'))
    assert any(c.get('Target')=='/library' and c.get('Type')=='Path' for c in template.findall('Config'))
    assert 'song-library:/library' in yaml.safe_load((root/'library_server/compose.yaml').read_text())['services']['library']['volumes']
    assert any(c.get('Target')=='8765' and c.get('Type')=='Port' for c in template.findall('Config'))
    assert not any(c.get('Target')=='OPENLIPS_BIND' for c in template.findall('Config'))
