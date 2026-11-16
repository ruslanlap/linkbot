import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent


def load(path):
    return yaml.safe_load((ROOT / path).read_text())


def run_scan(tmp_path, fix, status=0, path='docs'):
    step = load('action.yml')['runs']['steps'][0]
    fake = tmp_path / 'python3'
    fake.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$ARGS"\nexit "$STATUS"\n')
    fake.chmod(0o755)
    env = dict(os.environ, PATH=f'{tmp_path}:' + os.environ['PATH'],
               GITHUB_ACTION_PATH='/action directory', GITHUB_OUTPUT=str(tmp_path / 'output'),
               INPUT_PATH=path, INPUT_FIX=fix, STATUS=str(status), ARGS=str(tmp_path / 'args'))
    result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', step['run']], env=env)
    args = (tmp_path / 'args').read_text().splitlines() if (tmp_path / 'args').exists() else []
    output = (tmp_path / 'output').read_text() if (tmp_path / 'output').exists() else ''
    return result.returncode, args, output


@pytest.mark.parametrize('fix,status', [('false', 0), ('true', 0), ('true', 1), ('true', 2)])
def test_action_forwards_status_and_safe_arguments(tmp_path, fix, status):
    path = 'docs; touch injected'
    code, args, output = run_scan(tmp_path, fix, status, path)
    assert code == status
    assert args == ['/action directory/linkbot.py'] + (['--fix'] if fix == 'true' else []) + ['--', path]
    assert output == f'exit-code={status}\n'


def test_action_rejects_untrusted_fix(tmp_path):
    code, args, output = run_scan(tmp_path, 'true; touch injected')
    assert code == 2
    assert args == []
    assert output == 'exit-code=2\n'


def test_workflow_contract():
    action = load('action.yml')
    assert str(action['inputs']['fix']['default']).lower() == 'false'
    workflow = load('.github/workflows/linkbot.yml')
    triggers = workflow.get('on', workflow.get(True))
    assert 'schedule' in triggers and 'workflow_dispatch' in triggers
    assert workflow['permissions'] == {'contents': 'write', 'pull-requests': 'write'}
    steps = workflow['jobs']['links']['steps']
    scan = next(s for s in steps if s.get('id') == 'scan')
    assert scan['uses'].startswith('ruslanlap/linkbot@')
    assert scan['with']['fix'] == 'true'
    assert scan['continue-on-error'] is True
    gate = next(s for s in steps if s.get('id') == 'gate')
    for status, expected in [('0', 0), ('1', 0), ('2', 1), ('', 1), ('3', 1)]:
        env = dict(os.environ, SCAN_EXIT_CODE=status)
        assert subprocess.run(['bash', '-e', '-c', gate['run']], env=env).returncode == expected
    pr = next(s for s in steps if s.get('uses', '').startswith('peter-evans/create-pull-request@'))
    assert pr['with']['branch'] == 'linkbot/permanent-redirects'
    assert pr['with']['add-paths'] == '**/*.md'
