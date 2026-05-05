# Public Mock Client Acceptance Repository

Splendor's public mock client acceptance target is
[`splendor-dev/mock-client-acceptance`](https://github.com/splendor-dev/mock-client-acceptance).
It exists so external evaluators can exercise realistic Splendor workflows without private client
material.

The reviewed M17-P1.1 acceptance state is pinned to immutable refs:

- Healthy baseline tag: `m17-p1.1-acceptance-main`
  (`fa733da2a344cb55605a364f403aba9e290bbd62`)
- Source-refresh scenario tag: `m17-p1.1-source-refresh-scenario`
  (`ee4768ae12650e17f227bafa2a813e47af8ae77c`)

## Repository Contract

- Healthy `main` is safe for first-time evaluators.
- The default branch contains a small CLI/data project, human-authored authority docs, contradictory
  research notes, Splendor-generated workspace state, and recovery fixtures.
- Intentionally broken source state is isolated under `acceptance-fixtures/` or on scenario
  branches.
- `.splendorignore` excludes fixtures and runtime scratch paths from healthy-root discovery.
- M17-P1.1 validation should use the pinned tags above, not floating branch names.
- The repository includes real merged PR history for evaluator review:
  [#1](https://github.com/splendor-dev/mock-client-acceptance/pull/1),
  [#2](https://github.com/splendor-dev/mock-client-acceptance/pull/2), and
  [#3](https://github.com/splendor-dev/mock-client-acceptance/pull/3).

## Baseline Evaluation

Clone the pinned public repository baseline and run:

```bash
git clone --branch m17-p1.1-acceptance-main \
  https://github.com/splendor-dev/mock-client-acceptance.git
cd mock-client-acceptance
```

```bash
splendor lint
splendor health
splendor brief --agent-context "balance reconciliation rollout"
splendor suggest-next "reconciliation contradictions"
```

Expected result: lint and health pass on `main`, and the agent-context brief ranks the current
spec, rollout plan, CSV-first decision, and held-entry research above the stale JSONL research note.
With M17-P2.1 lifecycle-aware handoff, current, reviewed, or PR-linked authority should also rank
above superseded or archived planning context when those records are present.

## Source-Refresh Scenario

Use the pinned source-refresh scenario tag:

```bash
git fetch --tags
git switch --detach m17-p1.1-source-refresh-scenario
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
`state/manifests/sources/`. The ignored fixture files are force-committed in the pinned baseline so
fresh clones include `.mypy_cache/cache.py` and `.codex/session.log`.

## Renamed-Source Scenario

Copy `acceptance-fixtures/renamed-source/` from the public repository to a temporary working
directory and follow that fixture's README.

The fixture models active source path repair with `splendor source update-path` while retaining the
old path as historical provenance for existing run records.
