# v0.5.1 Retrieval and Handoff Retry Release Notes

`v0.5.1` is a narrow post-v0.5.0 evaluation release for sending Splendor back through the
`hocrgen` and `hocrsyngen` agent-handoff retry loops. It is still not the public v1 tag. The
purpose is to validate whether the handoff and retrieval fixes that landed after `v0.5.0` are
enough for those repos to reconsider Splendor as a day-to-day tool for coding-agent continuity.

## Release Purpose

This release packages the M20 retrieval closeout on top of the v0.5.0 durability baseline:

- `splendor query` uses deterministic runtime acronym phrase expansion for common
  code-and-research workflow terms, including shorthand such as `ASR` and the full phrase
  `automatic speech recognition`.
- Query-backed `brief --agent-context` paths benefit from the same local-first shorthand and
  full-phrase recovery without adding a persisted vector store, hosted service, database, or
  background worker.
- Deterministic regression fixtures now cover the hocrgen/hocrsyngen retry pattern where richer
  full-phrase evidence must beat acronym-only or stale acronym material under competition.
- Shorthand query fixtures now run in non-empty corpora, so acronym recovery is tested against
  direct acronym competitors and unrelated partial-phrase background material.
- Agent handoff regression coverage now checks both completion-aware current-state inference and
  query-backed full-phrase recovery for shorthand goals.
- The M20 planning docs now keep mutating web review workflows deferred to `M20-P2.1` after this
  retrieval/handoff retry release.

## Trial Focus

The next expected action after publishing `v0.5.1` is a fresh pair of external-style retry prompts:

- `hocrgen`: retry the completed-`F3b` to next-`F4c` planning handoff and judge whether Splendor now
  beats direct `rg`, `git`, and `gh` for starting the next implementation thread.
- `hocrsyngen`: retry the merged-`S4c` to next-`S4d` handoff and re-check whether cold-start state
  review plus current-state inference now feels safe enough for day-to-day agent use.

Both trials should install from the `v0.5.1` GitHub Release wheel rather than an editable checkout,
so the comparison is clean against the earlier `v0.5.0` and `v0.4.0` release-wheel evaluations.

## Validation Expectations

Before tagging `v0.5.1` after this preparation PR merges, run the full local validation suite from
the repository root and confirm green `main` CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run splendor lint
uv build
```

The package metadata for this preparation PR is `0.5.1` in `pyproject.toml`,
`src/splendor/__init__.py`, and `uv.lock`. Create the `v0.5.1` tag only after the release-prep PR
merges and `main` is green.
