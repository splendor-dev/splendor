# v0.2.0 Evaluation Release Notes

`v0.2.0` is the next evaluation release for sending Splendor back through the
SynthBanshee/Claude Code agent workflow. It is not the v1 tag. The release packages the completed
post-MVP stabilization, source-lifecycle, planning-authority, and reviewed compile/update work that
landed after the original alpha metadata.

## Release Purpose

This release is intended to give a coding agent using Splendor in a real companion repository a
cleaner, lower-noise operating loop:

- curated source manifests remain the durable source registry instead of broad automatic mirrors
- source discovery is non-mutating by default and produces candidate reports before registration
- source freshness, workspace refresh, supersession, pruning, and topic-ref migration cover the
  changed-source lifecycle without requiring manual manifest cleanup
- `splendor pr-summary --since main` gives reviewers a local generated-state handoff before PR
  publication
- planning-document authority metadata and task-oriented briefs rank the docs most relevant to a
  requested goal
- reviewed wiki compile/update work now has one-page proposal diffs, proposal hashes, explicit
  apply semantics, ranked target suggestions, and generated/maintained page separation
- health diagnostics point at concrete repair commands for known source, queue, and run problems

## Validation Expectations

Before tagging `v0.2.0` after this preparation PR merges, run the full local validation suite from
the repository root and confirm green `main` CI:

```bash
/Users/shaypalachy/.local/bin/uv run pytest
/Users/shaypalachy/.local/bin/uv run ruff format --check .
/Users/shaypalachy/.local/bin/uv run ruff check .
/Users/shaypalachy/.local/bin/uv run splendor lint
/Users/shaypalachy/.local/bin/uv run splendor health
/Users/shaypalachy/.local/bin/uv build
```

The package metadata for this preparation PR is `0.2.0` in both `pyproject.toml` and
`src/splendor/__init__.py`. Do not create or push the `v0.2.0` tag from this PR; tag only after the
release-prep PR merges and `main` is green.

## Current Issue State

As of this handoff, GitHub has no open issues for `splendor-dev/splendor`. The previously tracked
stabilization and agent-workflow issues, including #72, #47, #30, #37, #79, #86, #94, and the
related M14/M15 follow-ups, are closed or dispositioned in merged PRs. The next product step after
publishing `v0.2.0` is a fresh SynthBanshee/Claude Code evaluation run, not another pre-tag issue
slice.
