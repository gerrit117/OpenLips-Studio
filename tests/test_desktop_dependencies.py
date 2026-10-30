"""Platform constraints must protect Intel Macs without limiting other targets."""
from pathlib import Path
import tomllib

import pytest
from packaging.requirements import Requirement
from packaging.markers import default_environment


@pytest.mark.parametrize('system,machine,limited', [
    ('Darwin', 'x86_64', True), ('Darwin', 'arm64', False),
    ('Windows', 'AMD64', False), ('Linux', 'x86_64', False)])
def test_numba_binary_compatibility_constraint(system, machine, limited):
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))
    requirements = [Requirement(value) for value in project['project']['dependencies']]
    requirement = next(value for value in requirements if value.name == 'numba')
    environment = dict(default_environment(), platform_system=system, platform_machine=machine)
    assert requirement.marker.evaluate(environment) is limited
    assert '0.62.1' in requirement.specifier
    assert '0.63.0' not in requirement.specifier


def test_desktop_ci_does_not_fall_back_to_llvm_source_build():
    root = Path(__file__).resolve().parents[1]
    source = (root/'.github/workflows/studio.yml').read_text(encoding='utf-8')
    assert 'pip install --only-binary=numba,llvmlite -e ".[dev]"' in source
