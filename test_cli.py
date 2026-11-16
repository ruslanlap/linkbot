import contextlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import linkbot


class CLITests(unittest.TestCase):
    def test_check_fix_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'file.md'
            original = b'[x](https://example.com/old)\r\n'
            p.write_bytes(original)
            def fetch(url):
                return (301, '/new') if url.endswith('/old') else (200, None)
            with patch('linkbot.fetch', side_effect=fetch), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(linkbot.main([str(p)]), 1)
                self.assertEqual(p.read_bytes(), original)
                self.assertEqual(linkbot.main(['--fix', str(p)]), 0)
                self.assertEqual(p.read_bytes(), b'[x](https://example.com/new)\r\n')
                self.assertEqual(linkbot.main([str(p)]), 0)
            with patch('linkbot.fetch', return_value=(404, None)), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(linkbot.main([str(p)]), 1)

    def test_invalid_path_is_error(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(linkbot.main(['/definitely/not/linkbot/path']), 2)

    def test_cli_entrypoint_error(self):
        result = subprocess.run([os.sys.executable, 'linkbot.py', '/definitely/not/linkbot/path'], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_action_and_hook_execute_actual_cli(self):
        import yaml
        hook = yaml.safe_load(Path('.pre-commit-hooks.yaml').read_text())[0]
        action = yaml.safe_load(Path('action.yml').read_text())
        self.assertEqual(hook['entry'], 'linkbot')
        self.assertEqual(hook['language'], 'python')
        step = action['runs']['steps'][0]
        self.assertEqual(step['shell'], 'bash')
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, GITHUB_ACTION_PATH=str(Path.cwd()), INPUT_PATH='/definitely/not/linkbot/path', GITHUB_OUTPUT=str(Path(d)/'output'))
            result = subprocess.run(['bash', '-c', step['run']], env=env, capture_output=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('exit-code=2', Path(env['GITHUB_OUTPUT']).read_text())
            clean = Path(d) / 'clean.md'
            clean.write_text('No links\n')
            env['INPUT_PATH'] = str(clean)
            result = subprocess.run(['bash', '-c', step['run']], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn('exit-code=0', Path(env['GITHUB_OUTPUT']).read_text())

    def test_precommit_preserves_partially_staged_file_and_index(self):
        import shutil
        precommit = shutil.which('pre-commit')
        executable = shutil.which('linkbot')
        if not precommit or not executable:
            self.skipTest('pre-commit and installed linkbot are required')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(['git', 'init', '-q', d], check=True)
            file = root / 'doc.md'
            file.write_text('staged\n')
            subprocess.run(['git', 'add', 'doc.md'], cwd=d, check=True)
            staged = subprocess.check_output(['git', 'show', ':doc.md'], cwd=d)
            file.write_text('staged\nunstaged\n')
            config = root / '.pre-commit-config.yaml'
            config.write_text('repos:\n- repo: local\n  hooks:\n  - id: linkbot\n    name: LinkBot\n    language: system\n    entry: ' + executable + '\n    files: \\.md$\n')
            result = subprocess.run([precommit, 'run', 'linkbot', '--files', 'doc.md'], cwd=d, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(file.read_text(), 'staged\nunstaged\n')
            self.assertEqual(subprocess.check_output(['git', 'show', ':doc.md'], cwd=d), staged)
