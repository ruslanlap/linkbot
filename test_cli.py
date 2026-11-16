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

    def test_badge_and_anchor_check_fix_conservatively(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'odd name.md'
            original = ('[![badge](https://img.example/old)](https://example.com/old)\n'
                        '<a class="button" href="https://example.com/missing"><img src="https://img.example/old"></a>\n'
                        "<a href='https://example.com/old'>download</a>\n"
                        '![image](https://example.com/old)\n'
                        '\\[escaped](https://example.com/old)\n'
                        '`[code](https://example.com/old)`\n'
                        '~~~md\n<a href="https://example.com/old">code</a>\n~~~\n')
            p.write_text(original)
            def fetch(url):
                return {'https://example.com/old': (301, '/new'),
                        'https://example.com/new': (200, None),
                        'https://example.com/missing': (404, None)}[url]
            out = io.StringIO()
            with patch('linkbot.fetch', side_effect=fetch), contextlib.redirect_stdout(out):
                self.assertEqual(linkbot.main([str(p)]), 1)
                self.assertEqual(p.read_text(), original)
                self.assertEqual(linkbot.main(['--fix', str(p)]), 1)
            self.assertIn('odd name.md: https://example.com/missing', out.getvalue())
            self.assertEqual(p.read_text(), original.replace('](https://example.com/old)\n', '](https://example.com/new)\n', 1).replace("href='https://example.com/old'", "href='https://example.com/new'"))

    def test_latest_asset_check_and_fix(self):
        url = 'https://github.com/owner/repo/releases/latest/download/tool-1.3.0.zip'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'readme.md'
            original = f'[![download](https://img.example/badge)]({url})\n'
            p.write_text(original)
            def fetch(target):
                return (302, '/owner/repo/releases/download/v1.4.0/tool-1.3.0.zip') if target == url else (404, None)
            release = {'tag_name': 'v1.4.0', 'draft': False, 'prerelease': False,
                       'assets': [{'name': 'tool-1.4.0.zip'}]}
            with patch('linkbot.fetch', side_effect=fetch), patch('linkbot.latest_release', return_value=release), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(linkbot.main([str(p)]), 1)
                self.assertEqual(p.read_text(), original)
                self.assertEqual(linkbot.main(['--fix', str(p)]), 0)
            self.assertEqual(p.read_text(), original.replace('tool-1.3.0.zip', 'tool-1.4.0.zip'))

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
