# Splendor Agent Rules

## Scope

- Treat the repository contents as the source of truth.
- Keep this file static. Put dynamic task state in `.agent-plan.md`, not here.
- Do not overwrite or compress the long-form planning docs in `docs/`.

## Setup and Commands

- Install dev dependencies: `uv sync --dev`
- Run the CLI locally: `uv run splendor <command>`
- Format check: `uv run ruff format --check .`
- Lint: `uv run ruff check .`
- Tests: `uv run pytest`
- CI test-job command (with coverage): `uv run pytest --cov=splendor --cov-report=term-missing --cov-report=xml`
- Pre-commit sweep: `uv run pre-commit run --all-files`

## Branch and Commit Rules

- Use a descriptive branch name.
- Default agent branches should use `codex/<topic>`.
- Cleanup or tooling branches may use `refactor/<topic>`.
- Planning notation uses two levels:
  - milestone slices such as `M6-P1`
  - concrete PR sub-slices such as `M6-P1.1`, `M6-P1.2`, and `M6-P2.1`
- When a planned slice spans multiple PRs, every PR should carry the next available dotted
  sub-slice under that parent slice instead of reusing the parent notation as if it were a
  single-PR unit.
- Keep commits scoped to one logical change.
- Do not rewrite history on shared branches unless explicitly requested.
- Feature or PR work is not complete at local commit time, after local tests pass, or after the
  branch is committed locally. It only ends once the branch is pushed and a non-draft GitHub PR
  with a detailed description is open.
- Treat that publish step as a universal completion gate for feature work and PR work, not as an
  optional final polish step.
- Published PRs should carry intentional GitHub metadata:
  apply the appropriate labels, assign the PR to a milestone, and avoid leaving review-ready work
  as draft unless the user explicitly asks for a draft.
- Prefer repo-specific GitHub MCP tooling for PR metadata and fall back to `gh` only where the MCP
  surface is missing, such as creating a missing label or milestone or opening the PR itself.
- When finishing feature or PR work, explicitly verify that the published PR exists on GitHub and
  that its labels and milestone are set before treating the task as done.
- When a PR implements work from a plan, update the versioned planning state in the same PR:
  `.agent-plan.md`, `README.md`, and any affected human-facing planning document in `docs/`.
- PR titles, descriptions, and planning updates should use the concrete PR sub-slice notation when
  one exists, while still naming the parent milestone slice that the PR advances.

## Architecture Boundaries

- Keep repository layout changes aligned with `src/splendor/layout.py`.
- Use models in `src/splendor/schemas/` as the contract for persisted record shapes.
- `state/manifests/sources/` is the canonical machine-readable source registry.
- Prefer deterministic filesystem state over hidden caches or implicit runtime state.
- Do not add SQLite, background workers, OCR flows, or web UI code unless the task explicitly calls for them.

## CLI and State Expectations

- Current CLI surface lives in `src/splendor/cli.py` and `src/splendor/commands/`.
- Preserve deterministic CLI output and exit codes.
- Preserve idempotent file-writing behavior where commands already promise it.
- Validate schema-bound files instead of bypassing the models.

## When Changing Behavior

- If you change CLI behavior, update tests in `tests/` and any affected docs in `README.md` or `docs/ci_and_repo_automation.md`.
- If you change storage, manifests, or resolver behavior, update tests covering:
  - `add-source`
  - `ingest`
  - `health`
  - source resolver / registry behavior
- If you change GitHub workflow behavior or contributor automation, review `.github/workflows/` and `docs/ci_and_repo_automation.md`.

## Planning References

- Read `docs/splendor_product_spec.md` before changing product shape.
- Read `docs/splendor_mvp_to_v1_roadmap.md` before changing milestone scope.
- Read `docs/source_resolution_refactor_plan.md` before changing source registration or materialization behavior.
