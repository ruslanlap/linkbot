# LinkBot

English | [Українська](README.uk.md) | [简体中文](README.zh-CN.md)

Check Markdown HTTPS links for permanent redirects and 404s. The CLI, pre-commit hook and reusable action are read-only by default; `--fix` explicitly updates eligible redirects locally. They send HTTPS GET requests but never write to the network.

## CLI

Requires Python 3.9+ and pip. Install from a checkout (no runtime dependencies):

```sh
python3 -m pip install .
linkbot                    # check the current directory
linkbot docs README.md     # check directories and/or files
linkbot --fix docs         # edit eligible links; review the diff
```

Exit codes: **0** no findings (or fixes applied with no 404s), **1** redirects needing fixes in check mode or any observed 404, **2** invalid arguments or file I/O/UTF-8 errors. Network failures, unsupported URLs and other HTTP statuses are skipped, not errors: a clean result does **not** prove links work. Output lists the number of links to update (or updated), file names, and 404 entries. Repeated file names mean multiple links. `--fix` may leave earlier changes in place if a later file errors.

## pre-commit

Install [pre-commit](https://pre-commit.com/) separately, then add this to `.pre-commit-config.yaml` (the example pins a published version tag):

```yaml
repos:
  - repo: https://github.com/ruslanlap/linkbot
    rev: v0.2.0
    hooks:
      - id: linkbot
```

Run `pre-commit install` and `pre-commit run --all-files`. The hook checks passed Markdown files and never edits them or the Git index, including partially staged files. Fix separately using `linkbot --fix` and review and stage changes yourself. Checks make network requests and can be slow/offline-inconclusive.

## Reusable GitHub Action

Requires a checked-out repository, Python 3 and bash on the runner. This example pins a published version tag:

```yaml
jobs:
  links:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - id: links
        uses: ruslanlap/linkbot@v0.2.0
        with:
          path: docs
```

`path` defaults to `.` and is one file or directory. The new `fix` input accepts only `'true'` or `'false'` (default); `'true'` applies eligible fixes. Output `exit-code` is `0`, `1`, or `2`; the step itself fails on 1 or 2. Access it using `${{ steps.links.outputs.exit-code }}` (use `if: always()` or `continue-on-error` after failure). The action needs no token or write permissions and does not create PRs.

### Scheduled fix PRs

Copy [`.github/workflows/linkbot.yml`](.github/workflows/linkbot.yml) into the same path in your repository. It runs weekly or manually, invokes the published action with `fix: 'true'`, and groups changes in one PR via `peter-evans/create-pull-request`. It accepts exit 1 so fixes can be proposed alongside unresolved 404s, but blocks PR creation on exit 2 or missing status. A 404-only scan creates no PR; inspect the action log. Review every fix before merging. The workflow grants only contents and pull-requests write permissions; repository settings must also allow GitHub Actions to create PRs.

The workflow uses `v0.2.0`. It has not been tested with a live PR.

## Scope and safety

Simple inline Markdown HTTPS links, linked image badges, and single-line HTML anchors with quoted HTTPS hrefs are recognized; image sources, URLs with queries, code fences, lines containing backticks or backslashes, and other forms are skipped. Same-host 301/308 chains ending in 200 are fixed. A confirmed 404 GitHub `releases/latest/download` asset can also be updated when the public, unauthenticated latest-release API identifies exactly one asset whose name differs only by its stable release version; unavailable, ambiguous, draft or prerelease results are not fixed. API rate limits may prevent fixes. Anchors are retained, not validated. Private/non-public addresses and unsafe redirect targets are rejected. HTTP failures and inaccessible files during directory traversal can be missed. Redirects may change content: review all fixes. Avoid secrets in URLs.

The experimental `ghapp/` hosted GitHub App code remains in the repository but is unsupported and is not the recommended installation path.

## Development

For the full legacy and CLI suite, install `requirements.txt`, `pytest`, `pytest-subtests`, and `pyyaml`, then run `python3 -m pytest -q`.
