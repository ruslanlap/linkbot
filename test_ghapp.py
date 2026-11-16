"""Comprehensive tests for the LinkBot GitHub App backend.

All tests are fully offline – no network calls, no real GitHub tokens.
Tests cover: HMAC verification, JWT auth, webhook handling, scanner
orchestration, installation lifecycle, duplicate PR avoidance, tarball
safety, and configuration.
"""

import hashlib
import hmac
import io
import json
import os
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# Set required env vars BEFORE importing modules that might read them
os.environ.setdefault("LINKBOT_APP_ID", "12345")
os.environ.setdefault("LINKBOT_WEBHOOK_SECRET", "test-secret-do-not-use")
def _generate_test_key():
    """Generate a valid RSA key pair for testing."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()

_TEST_KEY = _generate_test_key()
os.environ.setdefault("LINKBOT_PRIVATE_KEY", _TEST_KEY)


class TestWebhookVerify(unittest.TestCase):
    """Test HMAC-SHA256 webhook signature verification."""

    def _sign(self, payload: bytes, secret: bytes = b"test-secret-do-not-use") -> str:
        sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    def test_valid_signature_accepted(self):
        from ghapp.webhook_verify import verify
        payload = b'{"action":"created"}'
        sig = self._sign(payload)
        self.assertTrue(verify(payload, sig))

    def test_invalid_signature_rejected(self):
        from ghapp.webhook_verify import verify
        payload = b'{"action":"created"}'
        self.assertFalse(verify(payload, "sha256=deadbeef" + "0" * 56))

    def test_missing_signature_rejected(self):
        from ghapp.webhook_verify import verify
        self.assertFalse(verify(b"data", None))
        self.assertFalse(verify(b"data", ""))

    def test_wrong_prefix_rejected(self):
        from ghapp.webhook_verify import verify
        self.assertFalse(verify(b"data", "sha1=abc123"))

    def test_tampered_payload_rejected(self):
        from ghapp.webhook_verify import verify
        payload = b'{"action":"created"}'
        sig = self._sign(payload)
        # Tamper with payload
        self.assertFalse(verify(b'{"action":"deleted"}', sig))

    def test_wrong_secret_rejected(self):
        from ghapp.webhook_verify import verify
        payload = b'{"action":"created"}'
        # Sign with wrong secret
        sig = self._sign(payload, secret=b"wrong-secret")
        self.assertFalse(verify(payload, sig))


class TestConfig(unittest.TestCase):
    """Test configuration loading."""

    def test_app_id_from_env(self):
        from ghapp.config import app_id
        with patch.dict(os.environ, {"LINKBOT_APP_ID": "99999"}):
            self.assertEqual(app_id(), "99999")

    def test_private_key_from_env(self):
        from ghapp.config import private_key
        with patch.dict(os.environ, {"LINKBOT_PRIVATE_KEY": "-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----"}):
            key = private_key()
            self.assertIn(b"BEGIN RSA PRIVATE KEY", key)

    def test_private_key_from_file(self):
        from ghapp.config import private_key
        with tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as f:
            f.write(b"-----BEGIN RSA PRIVATE KEY-----\nfile-key\n-----END RSA PRIVATE KEY-----")
            f.flush()
            try:
                with patch.dict(os.environ, {
                    "LINKBOT_PRIVATE_KEY": "",
                    "LINKBOT_PRIVATE_KEY_FILE": f.name,
                }):
                    key = private_key()
                    self.assertIn(b"file-key", key)
            finally:
                os.unlink(f.name)

    def test_missing_private_key_raises(self):
        from ghapp.config import private_key
        with patch.dict(os.environ, {
            "LINKBOT_PRIVATE_KEY": "",
            "LINKBOT_PRIVATE_KEY_FILE": "",
        }, clear=False):
            # Remove keys to force error
            env = os.environ.copy()
            env.pop("LINKBOT_PRIVATE_KEY", None)
            env.pop("LINKBOT_PRIVATE_KEY_FILE", None)
            with patch.dict(os.environ, {
                "LINKBOT_PRIVATE_KEY": "",
            }, clear=False):
                with patch("os.environ.get") as mock_get:
                    mock_get.side_effect = lambda k, d=None: "" if k.startswith("LINKBOT_PRIVATE_KEY") else os.environ.get(k, d)
                    with self.assertRaises(RuntimeError):
                        private_key()

    def test_webhook_secret_from_env(self):
        from ghapp.config import webhook_secret
        with patch.dict(os.environ, {"LINKBOT_WEBHOOK_SECRET": "my-secret"}):
            self.assertEqual(webhook_secret(), b"my-secret")

    def test_missing_webhook_secret_raises(self):
        from ghapp.config import webhook_secret
        with patch.dict(os.environ, {"LINKBOT_WEBHOOK_SECRET": ""}):
            with self.assertRaises(RuntimeError):
                webhook_secret()


class TestAuth(unittest.TestCase):
    """Test JWT generation and token caching."""

    def test_jwt_is_valid(self):
        """JWT should be decodable with the public key and have correct claims."""
        from ghapp.auth import _app_jwt
        import jwt as pyjwt
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        token = _app_jwt()
        # Decode with the same key (for test verification)
        key = load_pem_private_key(
            os.environ["LINKBOT_PRIVATE_KEY"].encode(),
            password=None,
        )
        public_key = key.public_key()
        decoded = pyjwt.decode(token, public_key, algorithms=["RS256"])
        self.assertEqual(decoded["iss"], "12345")
        # Check expiry is ~5 min from now
        self.assertGreater(decoded["exp"], time.time())
        self.assertLessEqual(decoded["exp"], time.time() + 360)

    def test_installation_token_caching(self):
        """Second call should use cache, not make a new API call."""
        from ghapp import auth

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {
            "token": "ghs_test123",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        mock_resp.raise_for_status = MagicMock()

        auth.clear_cache()
        with patch("requests.post", return_value=mock_resp) as mock_post:
            t1 = auth.installation_token(42)
            t2 = auth.installation_token(42)
            self.assertEqual(t1, "ghs_test123")
            self.assertEqual(t2, "ghs_test123")
            # Only one API call – second was cached
            self.assertEqual(mock_post.call_count, 1)

    def test_clear_cache_per_installation(self):
        from ghapp import auth
        auth._token_cache[1] = ("tok1", time.time() + 9999)
        auth._token_cache[2] = ("tok2", time.time() + 9999)
        auth.clear_cache(1)
        self.assertNotIn(1, auth._token_cache)
        self.assertIn(2, auth._token_cache)
        auth.clear_cache()
        self.assertEqual(len(auth._token_cache), 0)


class TestWebhookApp(unittest.TestCase):
    """Test the Flask webhook server."""

    def setUp(self):
        from ghapp.app import app
        self.app = app
        self.client = app.test_client()
        self.secret = b"test-secret-do-not-use"

    def _sign(self, payload: bytes) -> str:
        sig = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    def test_health_check(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ok")

    def test_webhook_rejects_unsigned(self):
        resp = self.client.post("/webhook",
                                data=b'{"action":"created"}',
                                content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_webhook_rejects_bad_signature(self):
        payload = b'{"action":"created"}'
        resp = self.client.post("/webhook",
                                data=payload,
                                content_type="application/json",
                                headers={"X-Hub-Signature-256": "sha256=bad"})
        self.assertEqual(resp.status_code, 401)

    def test_webhook_rejects_invalid_json(self):
        payload = b'not json'
        sig = self._sign(payload)
        resp = self.client.post("/webhook",
                                data=payload,
                                content_type="application/json",
                                headers={"X-Hub-Signature-256": sig})
        self.assertEqual(resp.status_code, 400)

    @patch("ghapp.scanner.scan_installation")
    def test_installation_created_triggers_scan(self, mock_scan):
        mock_scan.return_value = []
        payload = json.dumps({
            "action": "created",
            "installation": {"id": 123},
        }).encode()
        sig = self._sign(payload)
        resp = self.client.post("/webhook",
                                data=payload,
                                content_type="application/json",
                                headers={
                                    "X-Hub-Signature-256": sig,
                                    "X-GitHub-Event": "installation",
                                })
        self.assertEqual(resp.status_code, 202)

    @patch("ghapp.app.clear_cache")
    def test_installation_deleted_clears_cache(self, mock_clear):
        payload = json.dumps({
            "action": "deleted",
            "installation": {"id": 456},
        }).encode()
        sig = self._sign(payload)
        resp = self.client.post("/webhook",
                                data=payload,
                                content_type="application/json",
                                headers={
                                    "X-Hub-Signature-256": sig,
                                    "X-GitHub-Event": "installation",
                                })
        self.assertEqual(resp.status_code, 200)
        mock_clear.assert_called_once_with(456)

    def test_unknown_event_returns_200(self):
        payload = json.dumps({"action": "opened"}).encode()
        sig = self._sign(payload)
        resp = self.client.post("/webhook",
                                data=payload,
                                content_type="application/json",
                                headers={
                                    "X-Hub-Signature-256": sig,
                                    "X-GitHub-Event": "pull_request",
                                })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ignored")


class TestTarballSafety(unittest.TestCase):
    """Test that tarball extraction is safe against path traversal."""

    def _make_tarball(self, members: dict[str, bytes]) -> bytes:
        """Create an in-memory tarball with the given path->content entries."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, data in members.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    @patch("ghapp.auth.installation_token", return_value="ghs_fake")
    def test_path_traversal_blocked(self, _mock_token):
        """Files with .. in their path must not be extracted."""
        tarball = self._make_tarball({
            "repo-abc123/../../etc/passwd.md": b"# pwned",
            "repo-abc123/safe/readme.md": b"# Safe",
        })

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.iter_content.return_value = [tarball]
        mock_resp.raise_for_status = MagicMock()

        from ghapp.github_api import download_repo
        import shutil

        with patch("requests.get", return_value=mock_resp):
            tmpdir = download_repo(1, "owner", "repo")
            try:
                # The traversal file should NOT exist
                files = list(Path(tmpdir).rglob("*"))
                file_names = [f.name for f in files if f.is_file()]
                self.assertNotIn("passwd.md", file_names)
                # The safe file should exist
                self.assertIn("readme.md", file_names)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

    @patch("ghapp.auth.installation_token", return_value="ghs_fake")
    def test_only_markdown_extracted(self, _mock_token):
        """Non-markdown files should not be extracted."""
        tarball = self._make_tarball({
            "repo-abc123/readme.md": b"# Hello",
            "repo-abc123/script.sh": b"#!/bin/bash\nrm -rf /",
            "repo-abc123/code.py": b"import os; os.system('evil')",
        })

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.iter_content.return_value = [tarball]
        mock_resp.raise_for_status = MagicMock()

        from ghapp.github_api import download_repo
        import shutil

        with patch("requests.get", return_value=mock_resp):
            tmpdir = download_repo(1, "owner", "repo")
            try:
                files = list(Path(tmpdir).rglob("*"))
                file_names = [f.name for f in files if f.is_file()]
                self.assertIn("readme.md", file_names)
                self.assertNotIn("script.sh", file_names)
                self.assertNotIn("code.py", file_names)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

    @patch("ghapp.auth.installation_token", return_value="ghs_fake")
    def test_absolute_path_blocked(self, _mock_token):
        """Files with absolute paths must not be extracted."""
        tarball = self._make_tarball({
            "/etc/evil.md": b"# pwned",
            "repo-abc123/good.md": b"# OK",
        })

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.iter_content.return_value = [tarball]
        mock_resp.raise_for_status = MagicMock()

        from ghapp.github_api import download_repo
        import shutil

        with patch("requests.get", return_value=mock_resp):
            tmpdir = download_repo(1, "owner", "repo")
            try:
                files = list(Path(tmpdir).rglob("*"))
                file_names = [f.name for f in files if f.is_file()]
                self.assertNotIn("evil.md", file_names)
                self.assertIn("good.md", file_names)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)


class TestScanner(unittest.TestCase):
    def test_scan_no_changes_no_pr(self):
        from ghapp import scanner, github_api
        with tempfile.TemporaryDirectory() as tmpdir, \
             patch.object(github_api, "branch_exists", return_value=False), \
             patch.object(github_api, "get_default_branch", return_value="main"), \
             patch.object(github_api, "get_branch_sha", return_value="base"), \
             patch.object(github_api, "download_repo", return_value=Path(tmpdir)), \
             patch("linkbot.scan", return_value=([], [])), \
             patch.object(github_api, "create_pr") as create:
            result = scanner.scan_repo(1, "owner", "repo")
        self.assertIsNone(result["pr"])
        self.assertEqual(result["changes"], [])
        create.assert_not_called()

    def test_scan_handles_api_error(self):
        from ghapp import scanner, github_api
        with patch.object(github_api, "branch_exists", side_effect=Exception("API down")):
            result = scanner.scan_repo(1, "owner", "repo")
        self.assertIn("API down", result["error"])


class TestGitHubAPIHelpers(unittest.TestCase):
    """Test GitHub API helper functions."""

    @patch("ghapp.auth.installation_token", return_value="ghs_fake")
    def test_list_repos(self, _mock_token):
        from ghapp.github_api import list_repos

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "repositories": [
                {"name": "repo1", "owner": {"login": "org"}},
                {"name": "repo2", "owner": {"login": "org"}},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_resp.links = {}

        with patch("requests.get", return_value=mock_resp):
            repos = list_repos(1)
        self.assertEqual(len(repos), 2)
        self.assertEqual(repos[0]["name"], "repo1")

    @patch("ghapp.auth.installation_token", return_value="ghs_fake")
    def test_find_open_pr_returns_none_when_empty(self, _mock_token):
        from ghapp.github_api import find_open_pr

        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            pr = find_open_pr(1, "owner", "repo", "linkbot/permanent-redirects")
        self.assertIsNone(pr)

    @patch("ghapp.auth.installation_token", return_value="ghs_fake")
    def test_find_open_pr_returns_number(self, _mock_token):
        from ghapp.github_api import find_open_pr

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"number": 7}]
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            pr = find_open_pr(1, "owner", "repo", "linkbot/permanent-redirects")
        self.assertEqual(pr, 7)


class TestInstallationLifecycle(unittest.TestCase):
    """Test the full installation create → scan → delete lifecycle."""

    def setUp(self):
        from ghapp.app import app
        self.client = app.test_client()
        self.secret = b"test-secret-do-not-use"

    def _sign(self, payload: bytes) -> str:
        sig = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    @patch("ghapp.app.clear_cache")
    @patch("ghapp.scanner.scan_installation", return_value=[])
    def test_full_lifecycle(self, mock_scan, mock_clear):
        """Install → trigger scan → uninstall should work cleanly."""
        # 1. Installation created
        payload = json.dumps({
            "action": "created",
            "installation": {"id": 789},
        }).encode()
        resp = self.client.post("/webhook",
                                data=payload,
                                content_type="application/json",
                                headers={
                                    "X-Hub-Signature-256": self._sign(payload),
                                    "X-GitHub-Event": "installation",
                                })
        self.assertEqual(resp.status_code, 202)

        # Allow background thread to start (it's mocked, so completes instantly)
        import time
        time.sleep(0.1)

        # 2. Installation deleted
        payload2 = json.dumps({
            "action": "deleted",
            "installation": {"id": 789},
        }).encode()
        resp2 = self.client.post("/webhook",
                                 data=payload2,
                                 content_type="application/json",
                                 headers={
                                     "X-Hub-Signature-256": self._sign(payload2),
                                     "X-GitHub-Event": "installation",
                                 })
        self.assertEqual(resp2.status_code, 200)
        mock_clear.assert_called_with(789)


class TestScheduler(unittest.TestCase):
    """Test the scheduled scan driver."""

    @patch("ghapp.auth._app_jwt", return_value="app-jwt")
    @patch("ghapp.github_api.requests.get")
    def test_discovery_paginates_with_app_auth(self, get, jwt):
        from ghapp.scheduler import get_installation_ids
        first, second = MagicMock(), MagicMock()
        first.json.return_value = [{"id": i} for i in range(1, 101)]
        second.json.return_value = [{"id": 101}]
        get.side_effect = [first, second]
        self.assertEqual(get_installation_ids(), list(range(1, 102)))
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer app-jwt")
        self.assertEqual(get.call_args_list[1].kwargs["params"], {"per_page": 100, "page": 2})

    @patch("ghapp.github_api.requests.get")
    @patch("ghapp.auth._app_jwt", return_value="app-jwt")
    @patch("ghapp.scanner.scan_installation")
    def test_failed_pagination_does_not_scan_partial_results(self, scan, jwt, get):
        from ghapp.scheduler import run_once
        first, second = MagicMock(), MagicMock()
        first.json.return_value = [{"id": i} for i in range(100)]
        second.raise_for_status.side_effect = RuntimeError("API failed")
        get.side_effect = [first, second]
        with self.assertRaises(RuntimeError):
            run_once()
        scan.assert_not_called()

    @patch("ghapp.scanner.scan_installation", return_value=[{"repo": "a/b"}])
    @patch("ghapp.scheduler.get_installation_ids", side_effect=[[100, 200], [200]])
    def test_uninstalled_id_is_not_scanned_on_next_iteration(self, ids, scan):
        from ghapp.scheduler import run_once
        run_once()
        scan.reset_mock()
        run_once()
        scan.assert_called_once_with(200)


class TestPrivateKeyNeverLeaked(unittest.TestCase):
    """Ensure private key material doesn't appear in error messages or logs."""

    def test_auth_error_doesnt_contain_key(self):
        """If token acquisition fails, the error should not contain the key."""
        from ghapp import auth

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")
        mock_resp.json.return_value = {"message": "Bad credentials"}

        auth.clear_cache()
        with patch("requests.post", return_value=mock_resp):
            try:
                auth.installation_token(999)
            except Exception as e:
                error_msg = str(e)
                self.assertNotIn("BEGIN RSA PRIVATE KEY", error_msg)


if __name__ == "__main__":
    unittest.main()
