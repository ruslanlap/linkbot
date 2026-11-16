"""GitHub App authentication – JWT generation and installation token acquisition.

JWT lifetime is kept short (5 minutes, the GitHub maximum).  Installation
tokens are cached and refreshed before expiry.  Private keys never appear
in logs or exceptions.
"""

import time
from typing import Optional

import jwt
import requests

from . import config

# In-memory token cache: installation_id -> (token, expires_at_epoch)
_token_cache: dict[int, tuple[str, float]] = {}


def _app_jwt() -> str:
    """Create a short-lived JWT signed with the App's private key."""
    now = int(time.time())
    payload = {
        "iat": now - 60,          # clock skew tolerance
        "exp": now + (5 * 60),    # 5-minute max
        "iss": config.app_id(),
    }
    return jwt.encode(payload, config.private_key(), algorithm="RS256")


def installation_token(installation_id: int) -> str:
    """Return a valid installation access token, refreshing if needed.

    Tokens are scoped to the installation's repositories and permissions
    granted by the user – least-privilege by construction.
    """
    cached = _token_cache.get(installation_id)
    if cached:
        token, expires_at = cached
        if time.time() < expires_at - 60:  # 60-second safety margin
            return token

    token_jwt = _app_jwt()
    resp = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={
            "Authorization": f"Bearer {token_jwt}",
            "Accept": "application/vnd.github+json",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data["token"]
    # GitHub returns ISO-8601 expires_at; parse it roughly
    from datetime import datetime, timezone
    expires_at = datetime.fromisoformat(
        data["expires_at"].replace("Z", "+00:00")
    ).timestamp()
    _token_cache[installation_id] = (token, expires_at)
    return token


def clear_cache(installation_id: Optional[int] = None) -> None:
    """Drop cached tokens – e.g. after an installation is deleted."""
    if installation_id is None:
        _token_cache.clear()
    else:
        _token_cache.pop(installation_id, None)
