# v0.5.0 Post-v0.4 Durability Release Notes

`v0.5.0` is the post-v0.4 evaluation release for sending Splendor back to SynthBanshee and
similar agent-handoff trials after the accepted M19 durability sequence. It is still not the public
v1 tag. The purpose is to validate that v0.4's useful work-first handoff is now safer, more
completion-aware, and less brittle in cold-start repositories.

## Release Purpose

This release packages the post-v0.4 workflow safety and handoff-correctness work:

- Legacy mutating workflow commands now use preview-by-default semantics with explicit `--apply`
  where the M19 safety pass accepted that contract.
- Generated Evidence/Contradictions text is sanitized to prevent control-byte corruption in
  generated markdown and YAML.
- Source manifest provenance is refreshed when ingest or path-repair workflows rewrite manifest
  provenance.
- `brief --agent-context` and `suggest-next` reconcile stale planning-state text against recent
  mainline implementation evidence and ordered roadmap state, so completed slices do not remain the
  top suggested work.
- Agent handoff surfaces can show a bounded set of related open work threads instead of only the
  single best issue or PR.
- Files named by current, reviewed, or PR-linked authority docs receive deterministic read-first
  boosts when they exist in the repository.
- `splendor init` reports deterministic state review groups for configuration, human workspace,
  source/derived state, and runtime state, using the configured layout paths.
- Splendor-owned git subprocess lookup is PATH-safe and reports missing `git` distinctly from
  non-git worktrees.

## Trial Focus

The next expected action after publishing `v0.5.0` is a fresh SynthBanshee-oriented evaluation run.
The trial should explicitly check:

- whether `splendor brief --agent-context` still leads with current SynthBanshee implementation
  work before maintenance state
- whether completed roadmap slices are demoted when mainline history shows they have merged
- whether related open issues and policy-cited implementation/test files are visible enough for a
  coding agent to start without manual GitHub spelunking
- whether preview/apply behavior on legacy workflow commands is clear enough for agent-safe use
- whether generated markdown/YAML remains free of control-byte corruption
- whether cold-start initialization in a custom or hidden layout feels reviewable instead of
  creating surprising top-level churn
- whether malformed `PATH` entries do not crash git-aware handoff or source-provenance capture

## Validation Expectations

Before tagging `v0.5.0` after this preparation PR merges, run the full local validation suite from
the repository root and confirm green `main` CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run splendor lint
uv run splendor health
uv build
```

The package metadata for this preparation PR is `0.5.0` in both `pyproject.toml` and
`src/splendor/__init__.py`. Create the `v0.5.0` tag only after the release-prep PR merges and
`main` is green.
