# Public Mock Client Acceptance Repository

Splendor's public mock client acceptance target is
[`splendor-dev/mock-client-acceptance`](https://github.com/splendor-dev/mock-client-acceptance).
It exists so external evaluators can exercise realistic Splendor workflows without private client
material.

## Repository Contract

- Healthy `main` is safe for first-time evaluators.
- The default branch contains a small CLI/data project, human-authored authority docs, contradictory
  research notes, Splendor-generated workspace state, and recovery fixtures.
- Intentionally broken source state is isolated under `acceptance-fixtures/` or on scenario
  branches.
- `.splendorignore` excludes fixtures and runtime scratch paths from healthy-root discovery.

## Baseline Evaluation

Clone the public repository and run:

```bash
splendor lint
splendor health
splendor brief --agent-context "balance reconciliation rollout"
splendor suggest-next "reconciliation contradictions"
```

Expected result: lint and health pass on `main`, and the agent-context brief ranks the current
spec, rollout plan, CSV-first decision, and held-entry research above the stale JSONL research note.

## Source-Refresh Scenario

Use branch `scenario/source-refresh-lifecycle`:

```bash
git switch scenario/source-refresh-lifecycle
splendor source freshness
splendor workspace refresh --changed --ingest --prune-superseded --update-topic-refs --rebuild-index
splendor lint
splendor health
```

Expected result: Splendor detects changed curated sources, registers successor source versions,
ingests the refreshed sources, migrates maintained topic refs, and finishes with passing lint and
health.

## Polluted-Registry Scenario

Copy `acceptance-fixtures/polluted-registry/` from the public repository to a temporary working
directory and follow that fixture's README.

The fixture intentionally includes source manifests for ignored cache/local-agent paths and
duplicate active versions for `docs/specs/reconciliation.md`. The recovery path uses
`splendor source forget` and `splendor source reconcile` without manual deletion under
`state/manifests/sources/`.

## Renamed-Source Scenario

Copy `acceptance-fixtures/renamed-source/` from the public repository to a temporary working
directory and follow that fixture's README.

The fixture models active source path repair with `splendor source update-path` while retaining the
old path as historical provenance for existing run records.
