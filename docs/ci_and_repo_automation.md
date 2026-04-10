# CI and Repo Automation

This repository uses GitHub Actions for code quality checks and optional agent-facing repository
automation. The product runtime remains local-first; these workflows are repository operations, not
core Splendor runtime dependencies.

## `CI`

File: `.github/workflows/ci.yml`

Runs on:

- pull requests
- pushes to `main`

What it does:

- installs Python 3.12 and `uv`
- syncs development dependencies
- runs `ruff format --check`
- runs `ruff check`
- runs `pytest` with coverage
- emits `coverage.xml`
- uploads a `coverage-xml` artifact
- uploads coverage to Codecov
- publishes a `pr-agent-context` comment on pull requests

Permissions:

- `contents: read`
- `actions: read`
- `pull-requests: write` for PR context publication

Secrets and external dependencies:

- no secret is required for Codecov on a public repository
- `pr-agent-context` reuses local artifacts and does not require an extra token

## `pr-agent-context-refresh`

File: `.github/workflows/pr-agent-context-refresh.yml`

Runs on:

- pull request reviews
- pull request review comments
- completed external check runs

What it does:

- refreshes the managed PR context comment after review or check state changes
- reuses the `coverage-xml` artifact from the matching CI run when possible
- suppresses no-op refresh comments

Permissions:

- `contents: read`
- `actions: read`
- `pull-requests: write`

## `pre-commit.ci autofix trigger`

File: `.github/workflows/pre-commit-ci-autofix-trigger.yml`

Runs on:

- `pull_request_target` open, reopen, and synchronize events
- `status` updates, specifically `pre-commit.ci - pr` failures

What it does:

- checks whether the PR author matches a configured bot allowlist
- inspects GitHub check and status data for failing `pre-commit.ci` signals
- applies the `pre-commit.ci autofix` label when the downstream reusable workflow says it is safe

Permissions:

- `contents: read`
- `checks: read`
- `statuses: read`
- `pull-requests: write`
- `issues: write`

Secrets:

- defaults to `GITHUB_TOKEN`
- no additional secret is required unless a repository chooses to override the token

## `weekly-repo-review`

File: `.github/workflows/weekly-repo-review.yml`

Runs on:

- weekly schedule
- manual dispatch

What it does:

- invokes the reusable repo review automation
- collects deterministic repository signals
- asks the configured OpenAI model for repository findings
- opens or reopens deduplicated issues for actionable findings

Permissions:

- `contents: read`
- `pull-requests: read`
- `security-events: read`
- `issues: write`

Required secrets:

- `OPENAI_API_KEY`

Optional repository variables:

- `OPENAI_MODEL`

## How the workflows fit together

- `CI` is the primary quality gate.
- `pr-agent-context` turns CI, review, and failing-check state into a maintained PR handoff comment.
- `pre-commit.ci autofix trigger` bridges bot PRs and `pre-commit.ci` label-based autofix behavior.
- `weekly-repo-review` is scheduled maintenance, not a merge gate.
