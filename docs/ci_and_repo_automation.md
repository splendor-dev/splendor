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
  - pinned to `shaypal5/pr-agent-context/.github/workflows/pr-agent-context.yml@v4.0.19`
  - uses the `coverage-xml` artifact directly for patch coverage context

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
- scheduled fallback fanout every 15 minutes
- manual dispatch for explicit PR/SHA-targeted refreshes

What it does:

- refreshes the managed PR context comment after review or check state changes
- dispatches repo-owned fallback refresh runs for same-repo PRs when approval-gated bot events
  leave event-driven refresh stuck
- passes explicit PR number, base SHA, and head SHA overrides into the reusable workflow for
  fallback-triggered refreshes
- reuses the `coverage-xml` artifact from the matching CI run when possible
- suppresses no-op refresh comments
- includes outdated review threads when refreshing managed PR context
- dedupes scheduled fallback dispatches against both recent refresh comments and recent or in-flight
  refresh `workflow_dispatch` runs for the same PR head SHA

Permissions:

- `contents: read`
- `actions: read`
- `pull-requests: write`

Scheduled dispatcher details:

- enumerates only open same-repo PRs
- looks back over a bounded recent comment window
- isolates dispatch failures per PR instead of failing the entire fanout job
- uses the `actions/github-script` `github.rest.*` method names
- uses SHA-aware concurrency keys for dispatched refresh runs

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

Behavior without secret:

- the workflow still triggers, but the reusable review job is skipped cleanly when `OPENAI_API_KEY`
  is not configured

Optional repository variables:

- `OPENAI_MODEL`

## How the workflows fit together

- `CI` is the primary quality gate.
- `pr-agent-context` turns CI, review, and failing-check state into a maintained PR handoff comment.
- `pre-commit.ci autofix trigger` bridges bot PRs and `pre-commit.ci` label-based autofix behavior.
- `weekly-repo-review` is scheduled maintenance, not a merge gate.

## Planning update rule for PRs

When a pull request is opened against work that came from a tracked plan, the PR should update the
versioned planning documents as part of the same change. At minimum that means:

- `.agent-plan.md` for the current machine-readable task state
- `README.md` when its "what comes next" or milestone framing changes
- any relevant human-facing planning document under `docs/` that the PR advances, supersedes, or completes

This keeps the plan aligned with merged work and avoids stale roadmap or milestone guidance after a
planned slice lands.

## Agent completion rule for PR work

For agent-driven feature or PR work in this repository, local implementation is not the terminal
state. The work should be treated as complete only after:

- the branch is pushed
- a non-draft pull request is open on GitHub
- the pull request has a detailed description
- the pull request has intentional labels
- the pull request is assigned to the appropriate milestone

If any of those publication steps are still missing, the work is still in progress even if the code
changes are already committed locally.
