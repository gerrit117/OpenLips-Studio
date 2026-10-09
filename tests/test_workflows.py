from pathlib import Path
import yaml


class UniqueKeys(yaml.BaseLoader):
    pass


def mapping(loader, node):
    result = {}
    for key, value in node.value:
        name = loader.construct_object(key)
        if name in result:
            raise ValueError('Duplicate workflow key: ' + name)
        result[name] = loader.construct_object(value)
    return result


UniqueKeys.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)


def test_workflow_keys_and_job_dependencies():
    for path in Path('.github/workflows').glob('*.yml'):
        workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=UniqueKeys)
        for job in workflow['jobs'].values():
            needs = job.get('needs', [])
            if isinstance(needs, str):
                needs = [needs]
            assert all(name in workflow['jobs'] for name in needs)
