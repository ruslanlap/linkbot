"""Scan orchestrator – ties the existing linkbot scanner to GitHub API operations.

Downloads repo content via tarball (no git clone, no customer code execution),
runs the existing ``linkbot.scan()`` checker, and creates a PR
with the fixes.
"""

import logging
import shutil
from pathlib import Path

from . import github_api

logger = logging.getLogger("linkbot.scanner")

BRANCH = "linkbot/permanent-redirects"
PR_TITLE = "docs: update permanently redirected links"
COMMIT_MSG = "docs: update permanently redirected links"


def scan_repo(installation_id: int, owner: str, repo: str) -> dict:
    """Scan a single repo and open a PR if changes are found.

    Returns a summary dict with keys:
      - repo: "owner/repo"
      - changes: list of changed file paths
      - missing: list of "file: url" 404 entries
      - pr: PR number if created, or None
      - error: error message if scan failed, or None
    """
    import linkbot  # local import to keep module independent

    result: dict = {
        "repo": f"{owner}/{repo}",
        "changes": [],
        "missing": [],
        "pr": None,
        "error": None,
    }

    tmpdir = None
    try:
        if github_api.branch_exists(installation_id, owner, repo, BRANCH):
            logger.info("%s/%s: branch already exists; skipping", owner, repo)
            return result
        default_branch = github_api.get_default_branch(installation_id, owner, repo)
        base_sha = github_api.get_branch_sha(installation_id, owner, repo, default_branch)
        tmpdir = github_api.download_repo(installation_id, owner, repo, base_sha)
        root = Path(tmpdir)

        # Run the existing scanner
        changes, missing = linkbot.scan(root)
        changes = list(dict.fromkeys(changes))
        result["changes"] = changes
        result["missing"] = missing

        if not changes:
            logger.info("%s/%s: no changes", owner, repo)
            return result

        # Collect changed file contents
        file_changes: dict[str, tuple[str, str]] = {}
        for rel_path in changes:
            full = root / rel_path
            if full.exists():
                file_changes[rel_path] = (full.read_text(encoding="utf-8"),
                                          "100755" if full.stat().st_mode & 0o111 else "100644")

        if not file_changes:
            return result

        # Create the commit and branch
        github_api.create_commit_from_files(
            installation_id, owner, repo,
            base_sha, BRANCH, file_changes, COMMIT_MSG,
        )

        # Build PR body
        body_lines = [
            "LinkBot found same-host permanent redirects ending in HTTP 200.",
            "Review destination and anchor validity before merging.",
            "",
            f"**{len(file_changes)} file(s) updated.**",
        ]
        if missing:
            body_lines.append("")
            body_lines.append(f"**{len(missing)} broken link(s) found (not auto-fixed):**")
            for m in missing[:50]:  # cap to avoid giant PR bodies
                body_lines.append(f"- `{m}`")
            if len(missing) > 50:
                body_lines.append(f"- … and {len(missing) - 50} more")

        body = "\n".join(body_lines)

        pr_number = github_api.create_pr(
            installation_id, owner, repo, BRANCH, default_branch, PR_TITLE, body,
        )
        result["pr"] = pr_number
        logger.info("%s/%s: created PR #%d", owner, repo, pr_number)

    except Exception as exc:
        logger.exception("Error scanning %s/%s", owner, repo)
        result["error"] = str(exc)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)

    return result


def scan_installation(installation_id: int) -> list[dict]:
    """Scan all repos for a given installation."""
    repos = github_api.list_repos(installation_id)
    results = []
    for repo_data in repos:
        owner = repo_data["owner"]["login"]
        name = repo_data["name"]
        r = scan_repo(installation_id, owner, name)
        results.append(r)
    return results
