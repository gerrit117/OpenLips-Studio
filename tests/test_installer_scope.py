from pathlib import Path


def test_updates_offer_installation_scope_and_migrate_known_user_location():
    script = (Path(__file__).resolve().parents[1] / 'packaging/windows/studio.iss').read_text(encoding='utf-8')
    assert 'UsePreviousPrivileges=no' in script
    assert 'PrivilegesRequiredOverridesAllowed=dialog commandline' in script
    assert 'DefaultDirName={autopf}\\OpenLips Studio' in script
    assert "(OldVersion = '0.3.0-beta.1')" not in script
    assert "ExpandConstant('{localappdata}\\Programs\\OpenLips Studio')" in script
    assert 'ExecAsOriginalUser(Uninstaller' in script
