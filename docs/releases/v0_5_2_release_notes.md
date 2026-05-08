# v0.5.2 Current-Work Handoff Retry Release Notes

`v0.5.2` is a tiny post-`v0.5.1` evaluation release for sending Splendor back through the
`hocrgen` and `hocrsyngen` agent-handoff retry loops. It is still not the public v1 tag.

The release exists because the `v0.5.1` retry showed that retrieval had improved, but
`brief --agent-context` and `suggest-next` still promoted merged PR history above the current
planned slice. `v0.5.2` packages the post-`v0.5.1` current-work handoff fix so reviewers can
evaluate the corrected behavior from a release wheel instead of an editable checkout.

## Release Purpose

This release packages the M20 current-work handoff ranking fix on top of `v0.5.1`:

- `brief --agent-context` and `suggest-next` now extract current planned work from `.agent-plan.md`,
  README, and roadmap authority when the user asks for current or next roadmap work.
- Completed PRs, recent commits, and historical/generated review evidence are demoted to
  predecessor context for current-work goals instead of becoming the default next action.
- Open issue and PR work-thread behavior remains intact when a live thread is the real current
  work.
- The implementation remains runtime-only and local-first. It adds no hosted service, background
  worker, mandatory external API, web workflow, database, or persisted index state.
- The M20 mutating web review workflow work remains proposal-only and read-only in this release.

## Trial Focus

The intended retry question is narrow:

> Does Splendor now identify the current next `hocrgen` / `hocrsyngen` slice instead of leading
> with merged PR review history?

Recommended reviewer checks:

- In `hocrgen`, retry the current planning handoff after refreshing or ingesting current project
  state and judge whether Splendor names the active next slice before historical PR review work.
- In `hocrsyngen`, retry both cold-start and applied-ingest handoff flows and judge whether current
  planning authority is promoted into the work action instead of remaining buried in relevant
  matches.
- Compare against the `v0.5.1` retry findings in
  `docs/evaluations/v0_5_1_retry_findings.md`; this release targets the handoff-ranking blocker
  recorded there, not broader web mutation, vector search, or first-run state relocation.

Reviewers should install from the `v0.5.2` GitHub Release wheel rather than an editable checkout.

## Validation Expectations

Before tagging `v0.5.2` after this preparation PR merges, run the full local validation suite from
the repository root and confirm green `main` CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run splendor lint
uv run splendor health
uv build
```

The package metadata for this preparation PR is `0.5.2` in `pyproject.toml`,
`src/splendor/__init__.py`, and `uv.lock`. Create the `v0.5.2` tag only after the release-prep PR
merges and `main` is green.
