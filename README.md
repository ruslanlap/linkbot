# LinkBot

English | [Українська](README.uk.md) | [简体中文](README.zh-CN.md)

LinkBot finds permanently redirected Markdown links and proposes fixes in a pull request.

> **Experimental prototype.** No public GitHub App is registered or hosted, and there is no install button. GitHub API integration and PR creation have not been tested live. Do not use in production.

## How to try it

1. Register your own [GitHub App](https://docs.github.com/en/apps/creating-github-apps), host the server, and install the app on selected repositories. Grant Contents read/write, Pull requests read/write and Metadata read; subscribe to installation and installation_repositories events.
2. An installation webhook starts a scan. Run the scheduler separately for weekly scans; it discovers installations through the authenticated GitHub App API on every run.
3. Review any PR before merging. If `linkbot/permanent-redirects` already exists, the repository is skipped; the app does not update that branch.

**A scan containing only 404s creates no notification or PR.** No PR does not mean all links work.

### Server and scheduler

Install Python dependencies with `pip install -r requirements.txt`. Set `LINKBOT_APP_ID`, `LINKBOT_WEBHOOK_SECRET` and either `LINKBOT_PRIVATE_KEY_FILE` or `LINKBOT_PRIVATE_KEY` in the server environment. Never commit credentials. Run behind a publicly reachable HTTPS endpoint; point the GitHub App webhook to `/webhook`.

```bash
python3 -m flask --app ghapp.app:app run --host 127.0.0.1 --port 8080
```

This Flask development server is not a production server. To run the scheduler separately, provide the same app ID and private key:

```bash
python3 -c 'from ghapp.scheduler import run_scheduler; run_scheduler()'
```

The scheduler uses a weekly interval and fetches the full paginated installation list each time; uninstalled accounts disappear from the next discovery. An uninstall during an in-progress scan may still cause API errors. Failed discovery skips that iteration rather than scanning a partial list. Error handling, rate limiting, concurrent scans and live GitHub behavior require further work. Only run one scheduler instance; webhook-triggered scans can overlap it.

404-only notifications are not implemented. Issues would require Issues read/write permission and reliable idempotency across concurrent scans and retries; existing branch guards also skip scans. Use the Actions run summary for observed 404s instead.

## Alternative: GitHub Actions

Copy `linkbot.py` and `.github/workflows/linkbot.yml` into your repository. Enable GitHub Actions and allow it to create pull requests in repository settings. Run **Actions → LinkBot → Run workflow**; the workflow also runs weekly. Review the generated PR; the run summary lists observed 404s. This is not a GitHub App installation. The workflow has not been tested against a live repository.

## Scope and safety

Only simple Markdown HTTPS links and same-host 301/308 redirect chains ending in HTTP 200 are eligible for replacement. Images, query strings, code blocks, and some Markdown syntax are skipped. Original anchors are retained but not validated. Redirects do not guarantee equivalent content; review the diff. Public IP addresses are checked before connecting; do not include secrets in URLs. Failed checks and skipped links are not proof that links work.

## Local development

`python3 linkbot.py .` scans and **modifies** Markdown files in the current directory; review changes before committing. Install test dependencies with `pip install pytest pytest-subtests`, then run `python3 -m pytest -q`.
