from xml.etree import ElementTree as ET
import pytest
from library_server.unraid.recover_template import template


def inspected():
    return [dict(Name='/openlips', Config=dict(Image='ghcr.io/gerrit117/openlips-library:latest',
        Env=['PUID=99', 'PGID=100', 'PATH=/usr/bin']), HostConfig=dict(NetworkMode='bridge',
        PortBindings={'8765/tcp': [dict(HostIp='', HostPort='8877')]}),
        Mounts=[dict(Type='bind', Source='/mnt/user/My Songs & Games', Destination='/library', RW=True),
                dict(Type='bind', Source='/mnt/user/appdata/openlips', Destination='/data', RW=True)])]


def test_recovers_real_name_ports_mounts_and_escaped_paths():
    root = ET.fromstring(template(inspected()))
    assert root.findtext('Name') == 'openlips'
    assert root.findtext('WebUI') == 'http://[IP]:[PORT:8765]/'
    assert root.find("Config[@Target='/library']").text == '/mnt/user/My Songs & Games'
    assert root.find("Config[@Target='8765']").text == '8877'
    assert root.find("Config[@Target='PUID']").text == '99'


def test_refuses_unrelated_container_or_settings_loss():
    value = inspected()
    value[0]['Config']['Image'] = 'postgres:latest'
    with pytest.raises(ValueError):
        template(value)
    value = inspected()
    value[0]['Mounts'].append(dict(Type='bind', Source='/mnt/user/Other', Destination='/extra', RW=True))
    with pytest.raises(ValueError):
        template(value)
