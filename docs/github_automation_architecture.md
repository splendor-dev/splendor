# GitHub Automation Architecture

This repository layers several optional GitHub automations around a local-first Splendor codebase.
The goal is fast feedback for contributors and better handoff context for coding agents without
turning GitHub into the product runtime.

## Architecture overview

1. Pull requests run `CI` for formatting, linting, tests, and coverage.
2. The same CI workflow uploads `coverage.xml`, sends coverage to Codecov, and invokes
   `pr-agent-context` to publish a managed PR context comment.
3. Follow-up review and check events trigger `pr-agent-context-refresh` to keep that context
   current as comments and external checks evolve.
4. `pre-commit.ci autofix trigger` listens for bot PR events and late-arriving `pre-commit.ci`
   failures, then applies the `pre-commit.ci autofix` label when the reusable workflow decides the
   PR is eligible.
5. `weekly-repo-review` performs scheduled repository review and files or reopens issues for
   durable maintenance findings.

## Coverage and Codecov

- `coverage.xml` is produced in `CI` with `coverage.py`.
- The report is uploaded both as a GitHub artifact and to Codecov.
- `pr-agent-context` is configured to use the `coverage-xml` artifact as the source of patch
  coverage context rather than scraping Codecov checks.
- `codecov.yml` sets a conservative patch target of 70% to start and lets overall project coverage
  follow the current baseline.

## pre-commit and pre-commit.ci

- Local contributors use `.pre-commit-config.yaml`.
- `pre-commit.ci` is not activated from repository code, but the repository is prepared for it.
- The README includes a badge and local installation commands.
- The autofix-trigger workflow only labels eligible bot PRs; it does not replace local pre-commit
  usage or standard CI.

## `pre-commit-ci-autofix-trigger`

Pinned reusable workflow:

- `shaypal5/pre-commit-ci-autofix-trigger@v1.0.4`

Chosen behavior:

- PR-event job runs only for bot-authored PRs
- status-event job runs only when `pre-commit.ci - pr` reports failure
- default label is `pre-commit.ci autofix`
- default `GITHUB_TOKEN` is used

Permissions note:

- write access to issues and pull requests is required because label application uses issue-label
  endpoints

Caveats:

- `pre-commit.ci` itself still needs to be enabled in the SaaS
- if repository settings block implicit label creation, the label may need to be created once by a
  maintainer

## `pr-agent-context`

Pinned reusable workflow:

- `shaypal5/pr-agent-context@v4.0.18`
  - Refresh flow uses `include_outdated_review_threads: true` to keep managed PR context aligned
    with both active and outdated review discussions.

Chosen behavior:

- initial PR runs publish a managed context comment
- refresh runs are triggered on review activity and completed external checks
- refresh runs suppress no-op all-clear comments
- refresh runs include outdated review threads for richer PR context updates
- coverage comes from the `coverage-xml` artifact produced by CI
- the repository provides a custom prompt template at `.github/pr-agent-context-template.md`

Refresh flow:

1. `CI` completes and posts the initial managed comment.
2. A review, review-comment, or external check completion event fires.
3. `pr-agent-context-refresh` re-invokes the reusable workflow in refresh mode.
4. The latest actionable managed comment is refreshed with up-to-date unresolved comments, failing
   checks, and patch-coverage context.

## `repo-review-automation`

Pinned reusable workflow:

- `shaypal5/repo-review-automation@v1.0.2`

Chosen behavior:

- weekly Monday morning review
- `create_issues: true`
- dedupe by fingerprint
- reopen matching closed issues
- repo-local defaults live in `.github/repo-review.yml`

Expected outputs:

- GitHub Actions artifact bundle with review context and findings
- newly created issues for actionable findings
- reopened issues when the same fingerprint appears again and `reopen_closed_issues` is enabled

Required secret:

- `OPENAI_API_KEY`

Behavior without secret:

- the workflow gates itself before invoking the reusable review job, so repositories that have not
  configured `OPENAI_API_KEY` do not get noisy scheduled failures

Optional variable:

- `OPENAI_MODEL`

## Optional versus required pieces

Required for healthy repository maintenance:

- `CI`
- local pre-commit configuration

Optional, external-activation, or secret-gated pieces:

- Codecov project activation
- `pre-commit.ci` SaaS activation
- `OPENAI_API_KEY` for weekly repo review automation
- any future token override for label application in autofix-trigger
