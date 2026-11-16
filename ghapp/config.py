"""LinkBot GitHub App – configuration from environment variables.

Never import secrets at module level; functions read them lazily so tests
can patch ``os.environ`` or pass overrides without side-effects on import.
"""

import os


def app_id() -> str:
    """GitHub App ID (numeric string)."""
    return os.environ["LINKBOT_APP_ID"]


def private_key() -> bytes:
    """PEM-encoded RSA private key for JWT signing.

    Read from ``LINKBOT_PRIVATE_KEY`` (literal PEM) or, when that is not
    set, from the file at ``LINKBOT_PRIVATE_KEY_FILE``.  The key is never
    logged or included in error payloads.
    """
    pem = os.environ.get("LINKBOT_PRIVATE_KEY")
    if pem:
        return pem.encode()
    path = os.environ.get("LINKBOT_PRIVATE_KEY_FILE")
    if path:
        with open(path, "rb") as f:
            return f.read()
    raise RuntimeError("Set LINKBOT_PRIVATE_KEY or LINKBOT_PRIVATE_KEY_FILE")


def webhook_secret() -> bytes:
    """HMAC secret for webhook signature verification."""
    secret = os.environ.get("LINKBOT_WEBHOOK_SECRET", "")
    if not secret:
        raise RuntimeError("Set LINKBOT_WEBHOOK_SECRET")
    return secret.encode()
