"""Scheduled scan driver.

In production, run this module (or call ``run_scheduler``) as a long-lived
process alongside the webhook server.  It periodically enumerates all known
installations and triggers scans.

For real deployments you'd store installation IDs in a database.
This minimal version accepts them via environment variable.
"""

import logging
import os
import time

from . import scanner

logger = logging.getLogger("linkbot.scheduler")


def get_installation_ids() -> list[int]:
    """Return the list of installation IDs to scan.

    In production, this would query a database populated by
    installation webhook events.  Here we read from env for simplicity.
    """
    raw = os.environ.get("LINKBOT_INSTALLATION_IDS", "")
    if not raw.strip():
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def run_once() -> list[dict]:
    """Scan all known installations once."""
    ids = get_installation_ids()
    all_results: list[dict] = []
    for iid in ids:
        try:
            results = scanner.scan_installation(iid)
            all_results.extend(results)
        except Exception:
            logger.exception("Scan failed for installation %s", iid)
    return all_results


def run_scheduler(interval_seconds: int = 3600 * 24 * 7) -> None:
    """Run scans forever on the given interval (default: weekly)."""
    logger.info("Scheduler started, interval=%ds", interval_seconds)
    while True:
        try:
            run_once()
        except Exception:
            logger.exception("Scheduler iteration failed")
        time.sleep(interval_seconds)
