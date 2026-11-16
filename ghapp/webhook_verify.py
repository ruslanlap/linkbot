"""Webhook signature verification (HMAC-SHA256).

GitHub signs every webhook delivery with the shared secret.  We reject
requests whose ``X-Hub-Signature-256`` header does not match.
"""

import hashlib
import hmac

from . import config


def verify(payload: bytes, signature_header: str | None) -> bool:
    """Return True if the HMAC-SHA256 signature is valid.

    ``signature_header`` should be the value of ``X-Hub-Signature-256``,
    e.g. ``sha256=abc123...``.  Timing-safe comparison prevents
    length-extension and side-channel attacks.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        config.webhook_secret(), payload, hashlib.sha256
    ).hexdigest()
    received = signature_header[len("sha256="):]
    return hmac.compare_digest(expected, received)
