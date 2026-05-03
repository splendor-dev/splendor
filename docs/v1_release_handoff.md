# v1 Release Handoff

This checklist is the release handoff for `M13-P3.2`. It does not add runtime behavior. It records
the final v1 verification path, issue state, GitHub metadata expectations, known non-blockers, and
post-v1 queue after the `M13-P2` redesign and `M13-P3.1` release-hardening audit.

## Release Validation

Run these commands from the repository root before tagging or publishing a v1 release:

```bash
uv run pytest
uv run ruff format --check .
uv run ruff check .
uv run splendor lint
```

For a CI-equivalent test job with coverage:

```bash
uv run pytest --cov=splendor --cov-report=term-missing --cov-report=xml
```

Before publishing release notes, verify that:

- the `README.md` "What Comes Next" block, `.agent-plan.md`, and
  `docs/splendor_mvp_to_v1_roadmap.md` planning-state lines match
- `docs/splendor_product_spec.md` acceptance criteria still match shipped behavior
- `docs/schema_contracts.md` still names schema version `1` and legacy manifest compatibility
- `docs/quickstart.md` demonstrates the current safe source workflow
- `docs/ci_and_repo_automation.md` and `docs/github_automation_architecture.md` still describe
  GitHub automation as optional around the local CLI

## GitHub Handoff

Release PRs should be non-draft and should carry:

- a detailed body covering changes, validation, limitations, and follow-up work
- focused labels such as `type/docs`, `area/docs`, `area/planning`, and `release/post-mvp`
- the `Milestone 13` milestone when it exists
- explicit issue linkage for issues that are closed or intentionally kept open

For this handoff:

- #70 is closed and should remain the completed parent feedback loop for the `M13-P2` redesign
- #72 remains open as the parent source-refresh lifecycle and agent-workflow feedback loop
- #41-#46 are closed as completed v1 dogfood issues after closing comments named the shipped scope
  and any deferred work; #79 tracks the deferred mutating compile/update path from #41
- #47 remains open as the real ingest run-duration bug
- #30 remains open as post-v1 repo-scan registration performance work
- #37 remains open as post-v1 web document-list scaling work

## Known Non-Blockers

These items are intentionally not v1 release blockers:

- stable logical source identities above content-addressed source IDs
- `supersedes` / `superseded_by` source lifecycle semantics
- one-command full workspace refresh
- superseded generated-state pruning and topic-ref migration
- `splendor pr-summary --since main`
- authority and staleness metadata for living planning docs
- lower-noise generated-state review policies beyond the current reviewer-significance guidance
- ingest run-duration precision for #47
- repo-scan bulk registration optimization for #30
- web document-list scaling for #37

## Post-v1 Queue

The conservative next queue is:

1. Split #72 into child slices when implementation starts, beginning with stable logical source
   identity and source-supersession design.
2. Add the smallest source lifecycle slice that keeps `source freshness`, `source refresh`, topic
   refs, runs, and health checks coherent without breaking schema version `1` compatibility.
3. Add `splendor pr-summary --since main` only after source lifecycle churn is explicit enough to
   summarize reliably.
4. Keep #79 as the tracked post-v1 compile/update workflow rather than reopening #41 for deferred
   scope.
5. Keep #30 and #37 as independent performance/scaling follow-ups unless real repository use makes
   either one urgent.

Do not ask the SynthBanshee Claude agent for the major "try Splendor again" re-evaluation until
the source-lifecycle and generated-state review loop is materially improved. The planned retry
bundle is:

1. `M14-P0.1` Split #72 into child issues and assign release metadata.
2. `M14-P1.1` Stable logical source identities above content-addressed source IDs.
3. `M14-P1.2` Supersession-aware source refresh, so changed files do not leave stale runs, topic
   refs, or health failures for agents to clean manually.
4. `M14-P1.3` Safe workspace refresh path covering changed-source detection, refresh, ingest,
   index rebuild, and a health-clean end state.
5. `M14-P1.4` Superseded generated-state pruning and topic-ref migration.
6. `M14-P2.1` PR summary and lower-noise generated-state review handoff, including
   `splendor pr-summary --since main` or an equivalent reviewed output.

After those slices land, ask the SynthBanshee Claude agent to retry a comparable real planning or
repo-maintenance workflow and compare against the original #72 report. Before then, any retry
should be framed narrowly around safe discovery, freshness, and handoff only.

## Tagging Readiness

After the release PR merges, v1 tagging is ready when `main` has:

- package version metadata updated for the intended v1 tag in both `pyproject.toml` and
  `src/splendor/__init__.py`
- a release-notes entry or GitHub release draft that names completed M13 work, validation, and the
  explicit post-v1 queue
- green CI for formatting, linting, tests, and coverage
- a passing `splendor lint` planning-state check
- no open issue mislabeled as a v1 blocker

Use this final tagging sequence after those checks pass:

```bash
git switch main
git pull --ff-only origin main
git tag -a v1.0.0 -m "Splendor v1.0.0"
git push origin v1.0.0
uv build
```

Before publishing artifacts outside GitHub, verify the built wheel/sdist from `dist/` in a clean
environment with:

```bash
uv pip install dist/splendor-*.whl
splendor --version
```
