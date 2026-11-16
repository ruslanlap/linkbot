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
