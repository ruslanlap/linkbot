"""GitHub API helpers – cloning repos, creating/updating PRs, and managing branches.

All operations use per-installation tokens (least privilege).  Repo content
is fetched via the archive API (tarball), not ``git clone``, to avoid
running git commands that could execute hooks from customer repos.
"""

import io
import gzip
import shutil
import os
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

import requests

from . import auth

API = "https://api.github.com"
MAX_COMPRESSED_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


def _headers(installation_id: int) -> dict:
    token = auth.installation_token(installation_id)
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def list_installation_ids() -> list[int]:
    """List app installations, failing the whole discovery if any page fails."""
    ids = []
    page = 1
    while True:
        resp = requests.get(
            f"{API}/app/installations",
            headers={"Authorization": f"Bearer {auth._app_jwt()}",
                     "Accept": "application/vnd.github+json"},
            params={"per_page": 100, "page": page}, timeout=30,
        )
        resp.raise_for_status()
        installations = resp.json()
        if not isinstance(installations, list):
            raise ValueError("Invalid installations response")
        ids.extend(item["id"] for item in installations)
        if len(installations) < 100:
            return ids
        page += 1


def list_repos(installation_id: int) -> list[dict]:
    """List repositories accessible to this installation."""
    hdrs = _headers(installation_id)
    repos: list[dict] = []
    url = f"{API}/installation/repositories?per_page=100"
    while url:
        resp = requests.get(url, headers=hdrs, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        repos.extend(data.get("repositories", []))
        # Handle pagination
        url = resp.links.get("next", {}).get("url")
    return repos


def download_repo(installation_id: int, owner: str, repo: str,
                  ref: str = "HEAD") -> Path:
    """Download the repo tarball and extract markdown files only.

    Returns a temporary directory containing the extracted tree.
    Never executes customer code – tarball is extracted with filters.
    """
    tmpdir = tempfile.mkdtemp(prefix="linkbot-")
    try:
        with requests.get(
            f"{API}/repos/{owner}/{repo}/tarball/{ref}",
            headers=_headers(installation_id), timeout=120, stream=True,
        ) as resp:
            resp.raise_for_status()
            buf = io.BytesIO()
            for chunk in resp.iter_content(chunk_size=65536):
                if buf.tell() + len(chunk) > MAX_COMPRESSED_BYTES:
                    raise ValueError("compressed archive exceeds size limit")
                buf.write(chunk)
        buf.seek(0)
        with gzip.GzipFile(fileobj=buf) as gz:
            data = gz.read(MAX_UNCOMPRESSED_BYTES + 1)
        if len(data) > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("uncompressed archive exceeds size limit")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
            extracted_bytes = 0
            for member in tar:
                name = member.name
                if member.isfile():
                    extracted_bytes += member.size
                    if extracted_bytes > MAX_UNCOMPRESSED_BYTES:
                        raise ValueError("archive members exceed size limit")
                if member.sparse is not None:
                    continue
                if (not member.isfile() or name.startswith("/") or
                        ".." in name.split("/") or not name.endswith(".md")):
                    continue
                parts = name.split("/", 1)
                if len(parts) < 2 or not parts[1]:
                    continue
                dest = Path(tmpdir) / parts[1]
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
                os.chmod(dest, 0o755 if member.mode & 0o111 else 0o644)
        return Path(tmpdir)
    except BaseException:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise


def get_default_branch(installation_id: int, owner: str, repo: str) -> str:
    """Return the default branch name for the repo."""
    hdrs = _headers(installation_id)
    resp = requests.get(f"{API}/repos/{owner}/{repo}", headers=hdrs, timeout=15)
    resp.raise_for_status()
    return resp.json()["default_branch"]


def get_branch_sha(installation_id: int, owner: str, repo: str, branch: str) -> str:
    resp = requests.get(f"{API}/repos/{owner}/{repo}/git/ref/heads/{branch}",
                        headers=_headers(installation_id), timeout=15)
    resp.raise_for_status()
    return resp.json()["object"]["sha"]


def branch_exists(installation_id: int, owner: str, repo: str,
                  branch: str) -> bool:
    """Check if a branch exists."""
    hdrs = _headers(installation_id)
    resp = requests.get(
        f"{API}/repos/{owner}/{repo}/git/ref/heads/{branch}",
        headers=hdrs, timeout=15,
    )
    if resp.status_code == 404:
        return False
    resp.raise_for_status()
    return True


def create_or_update_branch(installation_id: int, owner: str, repo: str,
                            branch: str, sha: str) -> None:
    """Create a new branch; never update an existing ref."""
    requests.post(
        f"{API}/repos/{owner}/{repo}/git/refs",
        headers=_headers(installation_id),
        json={"ref": f"refs/heads/{branch}", "sha": sha}, timeout=15,
    ).raise_for_status()


def find_open_pr(installation_id: int, owner: str, repo: str,
                 head_branch: str) -> Optional[int]:
    """Return the PR number for an existing open PR from ``head_branch``, or None."""
    hdrs = _headers(installation_id)
    resp = requests.get(
        f"{API}/repos/{owner}/{repo}/pulls",
        headers=hdrs,
        params={"head": f"{owner}:{head_branch}", "state": "open"},
        timeout=15,
    )
    resp.raise_for_status()
    prs = resp.json()
    return prs[0]["number"] if prs else None


def create_pr(installation_id: int, owner: str, repo: str,
              head: str, base: str, title: str, body: str) -> int:
    """Create a pull request and return its number."""
    hdrs = _headers(installation_id)
    resp = requests.post(
        f"{API}/repos/{owner}/{repo}/pulls",
        headers=hdrs,
        json={"head": head, "base": base, "title": title, "body": body},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["number"]


def update_pr(installation_id: int, owner: str, repo: str,
              pr_number: int, body: str) -> None:
    """Update the body of an existing PR."""
    hdrs = _headers(installation_id)
    requests.patch(
        f"{API}/repos/{owner}/{repo}/pulls/{pr_number}",
        headers=hdrs,
        json={"body": body},
        timeout=15,
    ).raise_for_status()


def create_commit_from_files(
    installation_id: int, owner: str, repo: str,
    base_sha: str, branch: str,
    file_changes: dict[str, tuple[str, str]],
    message: str,
) -> str:
    """Create a commit on ``branch`` via the Git Data API (tree + commit).

    ``file_changes`` maps paths to (content, git mode).
    Returns the new commit SHA.  This avoids ``git push`` entirely.
    """
    hdrs = _headers(installation_id)

    # Create blobs
    tree_entries = []
    for path, (content, mode) in file_changes.items():
        resp = requests.post(
            f"{API}/repos/{owner}/{repo}/git/blobs",
            headers=hdrs,
            json={"content": content, "encoding": "utf-8"},
            timeout=15,
        )
        resp.raise_for_status()
        blob_sha = resp.json()["sha"]
        tree_entries.append({
            "path": path,
            "mode": mode,
            "type": "blob",
            "sha": blob_sha,
        })

    # The tree endpoint expects a tree SHA, not a commit SHA.
    resp = requests.get(f"{API}/repos/{owner}/{repo}/git/commits/{base_sha}",
                        headers=hdrs, timeout=15)
    resp.raise_for_status()
    base_tree = resp.json()["tree"]["sha"]
    resp = requests.post(
        f"{API}/repos/{owner}/{repo}/git/trees",
        headers=hdrs,
        json={"base_tree": base_tree, "tree": tree_entries},
        timeout=15,
    )
    resp.raise_for_status()
    tree_sha = resp.json()["sha"]

    # Create commit
    resp = requests.post(
        f"{API}/repos/{owner}/{repo}/git/commits",
        headers=hdrs,
        json={
            "message": message,
            "tree": tree_sha,
            "parents": [base_sha],
        },
        timeout=15,
    )
    resp.raise_for_status()
    commit_sha = resp.json()["sha"]

    # Update branch ref
    create_or_update_branch(installation_id, owner, repo, branch, commit_sha)

    return commit_sha
