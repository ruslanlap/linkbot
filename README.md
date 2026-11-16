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

Install [pre-commit](https://pre-commit.com/) separately, then add this to `.pre-commit-config.yaml` (the example pins a published commit):

```yaml
repos:
  - repo: https://github.com/ruslanlap/linkbot
    rev: 2f939a265060ea83d9a8f97ea5d6d4fd1b9291c1
    hooks:
      - id: linkbot
```

Run `pre-commit install` and `pre-commit run --all-files`. The hook checks passed Markdown files and never edits them or the Git index, including partially staged files. Fix separately using `linkbot --fix` and review and stage changes yourself. Checks make network requests and can be slow/offline-inconclusive.

## Reusable GitHub Action

Requires a checked-out repository, Python 3 and bash on the runner. This example pins a published commit:

```yaml
jobs:
  links:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - id: links
        uses: ruslanlap/linkbot@2f939a265060ea83d9a8f97ea5d6d4fd1b9291c1
        with:
          path: docs
```

`path` defaults to `.` and is one file or directory. Output `exit-code` is `0`, `1`, or `2`; the step itself fails on 1 or 2. Access it using `${{ steps.links.outputs.exit-code }}` (use `if: always()` or `continue-on-error` for subsequent steps after failure). The action requires no token or write permissions; `contents: read` is for checkout. It does not fix files or create PRs. The bundled `.github/workflows/linkbot.yml` is a separate scheduled/manual workflow for this repository, uses `--fix` and may create a PR with contents and pull-requests write permissions; GitHub settings must permit Actions to create PRs. It is not live-verified. 404-only scans create no PR; inspect the run summary.

## Scope and safety

Only simple inline Markdown HTTPS links are recognized; images, URLs with queries, code fences, lines containing backticks, and other Markdown forms are skipped. Only same-host 301/308 chains ending in 200 are fixed. Anchors are retained, not validated. Private/non-public addresses and unsafe redirect targets are rejected. HTTP failures and inaccessible files during directory traversal can be missed. Redirects may change content: review all fixes. Avoid secrets in URLs.

The experimental `ghapp/` hosted GitHub App code remains in the repository but is unsupported and is not the recommended installation path.

## Development

For the full legacy and CLI suite, install `requirements.txt`, `pytest`, `pytest-subtests`, and `pyyaml`, then run `python3 -m pytest -q`.
