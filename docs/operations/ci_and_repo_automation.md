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
  - uses the floating stable major workflow ref
    `shaypal5/pr-agent-context/.github/workflows/pr-agent-context.yml@v4`
  - this floating `@v4` ref, together with `tool_ref: v4`, is intentional repository policy for
    `pr-agent-context`; it should not be treated as a review finding unless the policy itself is
    being revisited
  - uses the `coverage-xml` artifact directly for patch coverage context

Permissions:

- `contents: read`
- `actions: read`
- `pull-requests: write` for PR context publication

Secrets and external dependencies:

- no secret is required for Codecov on a public repository
- `pr-agent-context` reuses local artifacts and does not require an extra token

## `Splendor maintenance`

File: `.github/workflows/splendor-maintenance.yml`

Runs on:

- pull requests
- pushes to `main`
- nightly schedule

What it does:

- installs Python 3.12 and `uv`
- syncs development dependencies
- runs `uv run splendor lint` on pull requests and pushes to `main`
- runs `uv run splendor health` on the nightly schedule
- uploads generated lint and health reports as GitHub Actions artifacts

Permissions:

- `contents: read`

Secrets and external dependencies:

- no secret is required
- the workflow uses the local Splendor CLI and does not make GitHub required for local runtime use

## `Splendor generated-change PR`

File: `.github/workflows/splendor-generated-change-pr.yml`

Runs on:

- weekly schedule
- manual dispatch

What it does:

- checks out `main`
- installs Python 3.12 and `uv`
- syncs development dependencies
- runs `uv run splendor repo refresh` in safe non-registering mode
- runs `uv run splendor lint`
- uploads generated lint reports as a GitHub Actions artifact
- opens or updates a PR from `codex/splendor-generated-repo-refresh` when deterministic generated
  state changes exist

Reviewed output paths:

- `wiki/**`
- `raw/sources/**`
- source manifests, queue/run records, derived artifacts, and explicit reports when they are part
  of the reviewed generated workspace update

Permissions:

- `contents: write`
- `pull-requests: write`

Secrets and external dependencies:

- no secret is required
- PR creation uses `peter-evans/create-pull-request@v8` with the repository `GITHUB_TOKEN`
- GitHub documents that most events caused by `GITHUB_TOKEN`, except `workflow_dispatch` and
  `repository_dispatch`, do not create follow-up workflow runs automatically:
  <https://docs.github.com/actions/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow#triggering-a-workflow-from-a-workflow>

Review expectations:

- confirm generated wiki/source-registry changes match the repository state
- confirm the generating workflow's Splendor lint job passed
- distinguish reviewer-significant generated artifacts from mechanical timestamp-only churn
- manually dispatch or rerun normal CI if repository policy requires checks on the generated PR

## `Release artifacts`

File: `.github/workflows/release-artifacts.yml`

Runs on:

- `v*` tag pushes
- manual dispatch for an existing tag

What it does:

- checks out the selected tag
- installs Python 3.12 and `uv`
- verifies that the tag version matches `pyproject.toml` and `src/splendor/__init__.py`
- runs `uv build`
- smoke-installs the built wheel and exercises the installed CLI with `splendor --version`,
  `splendor --help`, `splendor init`, and `splendor lint`
- uploads `dist/*` as a GitHub Actions artifact
- requires the matching GitHub Release to already exist with release notes
- uploads the wheel and source distribution to that release

Permissions:

- `contents: write`

Secrets and external dependencies:

- no secret is required
- release upload uses the repository `GITHUB_TOKEN` through the GitHub CLI

## `planning-validator`

File: `.github/workflows/planning-validator.yml`

Runs on:

- manual dispatch only during the first client-repo pilot

What it does:

- checks that `OPENAI_API_KEY` is configured before invoking the reusable workflow
- invokes
  `shaypal5/planning-validator/.github/workflows/reusable-planning-validator.yml@017c24056d7fca224285f1a395d3afa8db721182`
- validates configured planning and tracking markdown against recent merged PR evidence
- opens or updates one draft PR from `automation/planning-validator` when evidence-backed planning
  updates are proposed

Reviewed output paths:

- `README.md`
- `.agent-plan.md`
- `docs/splendor_mvp_to_v1_roadmap.md`
- `docs/splendor_product_spec.md`
- `planning/tasks/*.md`

The reusable workflow is pinned to an immutable `planning-validator` commit for the pilot. Move to a
version tag once `planning-validator` publishes a release tag suitable for client repositories.

Explicitly ignored or forbidden paths include source, tests, workflows, repository automation config,
generated state, raw imports, reports, derived files, examples, and wiki pages. The pilot is
intentionally manual-only until at least one generated PR has been reviewed.

Permissions:

- `contents: write`
- `issues: write`
- `pull-requests: write`

Required secrets:

- `OPENAI_API_KEY`

Behavior without secret:

- the workflow still triggers, but the reusable planning-validator job is skipped cleanly when
  `OPENAI_API_KEY` is not configured

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

## `Claude Code Review`

File: `.github/workflows/claude-code-review.yml`

Runs on:

- after the CI workflow completes on a pull request (via `workflow_run`)
- issue comments containing `@claude` on pull requests (interactive follow-up)

What it does:

- gates automatic PR review on the triggering CI run's `lint` and `test` jobs only
- does not gate automatic PR review on `PR agent context`
- checks out the triggering pull request head SHA for automatic reviews
- passes the pull request number explicitly to Claude
- runs an automated code review on every pull request using `anthropics/claude-code-action`
- asks Claude to always post a top-level PR review summary comment, even when no concrete issues
  are found
- responds to `@claude` mentions in PR comments for interactive follow-up questions
- uses the Claude Code action's default model

Permissions:

- `contents: read`
- `actions: read`
- `pull-requests: write`
- `issues: write`

Required secrets:

- `PR_REVIEWS_ANTHROPIC_API_KEY`

## How the workflows fit together

- `CI` is the primary quality gate.
- `Splendor maintenance` runs repository/workspace integrity checks and publishes their reports as
  artifacts.
- `Splendor generated-change PR` proposes deterministic repo-refresh output as a reviewable PR
  without making GitHub part of the core runtime.
- `Release artifacts` publishes tag-built wheels and source distributions on GitHub Releases for
  lower-friction trial installs.
- `Claude Code Review` provides automated AI code review after CI `lint` and `test` pass, plus
  interactive follow-up.
- `pr-agent-context` turns CI, review, and failing-check state into a maintained PR handoff comment.
  Local `brief --agent-context` and `suggest-next` output may include ranked authority docs from
  `splendor.yaml`, but workflow comments remain GitHub-state summaries rather than document
  authority validators.
- `pre-commit.ci autofix trigger` bridges bot PRs and `pre-commit.ci` label-based autofix behavior.
- `weekly-repo-review` is scheduled maintenance, not a merge gate.

## Evaluation-release and v1 hardening boundaries

The current automation layer supports CI, maintenance reports, generated-change PRs, PR context
refresh, review automation, and optional weekly repo review. Source lifecycle, workspace refresh,
and `splendor pr-summary --since main` remain local CLI contracts; GitHub workflows can report or
package their output, but they do not replace the operator-reviewed local validation path.

`docs/releases/v1_release_handoff.md` remains the historical v1-style checklist that connects local
validation, GitHub PR metadata, issue state, and known non-blockers.
`docs/releases/v0_2_0_release_notes.md` records the earlier v0.2 evaluation tag, and
`docs/operations/release_artifacts.md` names GitHub Release wheels as the canonical trial-install
channel for v0.3 and later evaluators. GitHub automation remains supporting
infrastructure around the local CLI, not a substitute for the explicit validation commands named in
that handoff.

## Planning update rule for PRs

When a pull request is opened against work that came from a tracked plan, the PR should update the
versioned planning documents as part of the same change. At minimum that means:

- `.agent-plan.md` for the current machine-readable task state
- `README.md` when its "what comes next" or milestone framing changes
- any relevant human-facing planning document under `docs/` that the PR advances, supersedes, or completes

This keeps the plan aligned with merged work and avoids stale roadmap or milestone guidance after a
planned slice lands.

Use two-level planning notation in those updates:

- parent planned slices such as `M6-P1`
- concrete PR sub-slices such as `M6-P1.1`, `M6-P1.2`, and `M6-P2.1`

When one planned slice takes multiple PRs, each PR should use the next dotted sub-slice in its
title, body, and plan updates instead of pretending the parent slice maps one-to-one with a single
PR.

Structured planning-state blocks must use these synchronized labels:

- `Previous completed PR sub-slice`
- `Current planned slice`
- `Current PR sub-slice`
- `Current PR lifecycle`
- `Next planned slice`
- `Next planned PR sub-slice`

Use `Current PR lifecycle: branch=in-progress; main=merged`. This lets one committed planning
state read correctly while a branch is open and after it lands on `main`: the current PR sub-slice
is in progress on feature branches and merged on `main`.

## Agent completion rule for PR work

For agent-driven feature or PR work in this repository, local implementation is not the terminal
state. Treat GitHub publication as a mandatory completion gate, not as optional follow-up. The work
should be treated as complete only after:

- the branch is pushed
- a non-draft pull request is open on GitHub
- the pull request has a detailed description
- the pull request has intentional labels
- the pull request is assigned to the appropriate milestone

Prefer repo-specific GitHub MCP tooling for PR metadata updates and use `gh` only for operations
the MCP surface does not support cleanly, such as creating a missing label or milestone or opening
the PR itself.

If any of those publication steps are still missing, the work is still in progress even if the code
changes are already committed locally.

For Splendor-generated state changes, run `splendor pr-summary --since main` before publication
when practical. The command is read-only and uses local merge-base git state plus existing
lint/health reports to explain curated source changes, maintained wiki edits, source-summary
changes, and mechanical queue/run/report churn for reviewers. It labels lint/health status as
latest local report state; it does not replace the required validation commands or GitHub metadata
checks.

For source-registry recovery PRs, use `splendor source forget` in preview mode before applying any
cleanup. Applied recovery changes should be reviewed as intentional source-registry maintenance:
selected manifests and source-owned generated state may be removed, while residual maintained
wiki/planning references should remain visible in the command output and PR description.
Use `splendor source reconcile` in preview mode before applying duplicate canonical source-version
repairs. Applied reconciliation changes should be limited to source manifest lifecycle links and
should leave generated pages, maintained wiki pages, queue records, and run records untouched.
