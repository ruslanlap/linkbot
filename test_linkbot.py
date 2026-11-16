import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import linkbot


class LinkBotTests(unittest.TestCase):
    def test_permanent_redirect_is_updated_and_404_reported(self):
        def fetch(url):
            return {'https://example.com/old': (301, '/new'),
                    'https://example.com/new': (200, None),
                    'https://example.com/missing': (404, None)}[url]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.md'
            p.write_text('[old](https://example.com/old#part) [bad](https://example.com/missing)\n')
            with patch('linkbot.fetch', side_effect=fetch):
                changes, missing = linkbot.scan(Path(d))
            self.assertEqual(p.read_text(), '[old](https://example.com/new#part) [bad](https://example.com/missing)\n')
            self.assertEqual(len(changes), 1)
            self.assertEqual(missing, ['a.md: https://example.com/missing'])

    def test_latest_github_asset_version_repair(self):
        old = 'https://github.com/owner/repo/releases/latest/download/tool-1.3.0-x64.zip'
        new = old.replace('1.3.0', '1.4.0')
        release = {'tag_name': 'v1.4.0', 'draft': False, 'prerelease': False,
                   'assets': [{'name': 'tool-1.4.0-x64.zip'}]}
        def fetch(url):
            return (302, '/owner/repo/releases/download/v1.4.0/tool-1.3.0-x64.zip') if url == old else (404, None)
        with patch('linkbot.fetch', side_effect=fetch), patch('linkbot.latest_release', return_value=release, create=True):
            self.assertEqual(linkbot.resolve(old), (new, False))
        for bad in [dict(release, prerelease=True), dict(release, draft=True),
                    dict(release, assets=[]), dict(release, assets=release['assets'] * 2),
                    dict(release, tag_name='v1.4.0-rc1')]:
            with self.subTest(bad=bad), patch('linkbot.fetch', side_effect=fetch), patch('linkbot.latest_release', return_value=bad, create=True):
                self.assertEqual(linkbot.resolve(old), (None, True))

        ambiguous = old.replace('tool-1.3.0-x64.zip', 'tool-1.3.0-2.0.0.zip')
        with patch('linkbot.fetch', return_value=(404, None)), patch('linkbot.latest_release', create=True) as api:
            self.assertEqual(linkbot.resolve(ambiguous), (None, True))
            self.assertEqual(linkbot.resolve('https://example.com/missing'), (None, True))
            api.assert_not_called()

    def test_redirects_fail_closed(self):
        for target in ['http://example.com/new', 'https://evil.com/new', '/new#other', 'https://user:pass@example.com/new', '/new?token=secret']:
            with self.subTest(target=target), patch('linkbot.fetch', return_value=(301, target)):
                self.assertIsNone(linkbot.resolve('https://example.com/old#part')[0])
        with patch('linkbot.fetch', side_effect=[(302, '/new'), (200, None)]):
            self.assertIsNone(linkbot.resolve('https://example.com/old')[0])
        with patch('linkbot.fetch', side_effect=[(301, '/new'), (404, None)]):
            self.assertIsNone(linkbot.resolve('https://example.com/old')[0])

    def test_private_dns_and_sensitive_urls_rejected(self):
        for url in ['https://127.0.0.1/', 'https://user:pass@example.com/', 'https://example.com/?token=secret', 'http://example.com/']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                linkbot.fetch(url)
        with patch('socket.getaddrinfo', return_value=[(2, 1, 6, '', ('10.0.0.1', 443))]):
            with self.assertRaises(ValueError):
                linkbot.fetch('https://example.com/')

    def test_report_escapes_newlines(self):
        with patch('linkbot.scan', return_value=([], ['file\n::error::injected'])):
            with patch('sys.argv', ['linkbot']):
                from io import StringIO
                output = StringIO()
                with patch('sys.stdout', output):
                    linkbot.main()
                self.assertNotIn('\n::error::', output.getvalue())

    def test_images_and_fenced_code_are_not_modified(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.md'
            original = '![image](https://example.com/old)\n```md\n[x](https://example.com/old)\n```\n'
            p.write_text(original)
            with patch('linkbot.fetch', side_effect=lambda u: (301, '/new') if u.endswith('/old') else (200, None)):
                linkbot.scan(Path(d))
            self.assertEqual(p.read_text(), original)

    def test_only_markdown_destinations_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.md'
            p.write_text('https://example.com/old\n[x](https://example.com/old)\n')
            with patch('linkbot.fetch', side_effect=lambda u: (301, '/new') if u.endswith('/old') else (200, None)):
                linkbot.scan(Path(d))
            self.assertEqual(p.read_text(), 'https://example.com/old\n[x](https://example.com/new)\n')

if __name__ == '__main__':
    unittest.main()
