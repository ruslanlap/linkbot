"""Scheduled scan driver.

In production, run this module (or call ``run_scheduler``) as a long-lived
process alongside the webhook server. It discovers installations from GitHub
on each iteration and triggers scans.
"""

import logging
import time

from . import scanner, github_api

logger = logging.getLogger("linkbot.scheduler")


def get_installation_ids() -> list[int]:
    """Fetch a complete fresh installation list before starting any scans."""
    return github_api.list_installation_ids()


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
